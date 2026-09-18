from fastapi.testclient import TestClient

from mesh_api.app import create_app
from mesh_api.config import Settings
from mesh_api.pipeline import PipelineAdapters, run_pipeline
from mesh_api.adapters.mock import (
    MockMeshRecoverer,
    MockPersonDetector,
    MockPersonTracker,
    MockVideoIngestor,
)
from mesh_api.models import JobStage


def make_client(scenario="two_person_crossing", *, max_seconds=120, mesh_unavailable=False):
    settings = Settings(max_video_seconds=max_seconds, target_mesh_fps=24)
    app = create_app(settings=settings, scenario=scenario, mesh_unavailable=mesh_unavailable)
    return TestClient(app)


def make_adapters(scenario="two_person_crossing"):
    return PipelineAdapters(
        ingestor=MockVideoIngestor(),
        detector=MockPersonDetector(scenario=scenario),
        tracker=MockPersonTracker(),
        mesh_recoverer=MockMeshRecoverer(),
    )


def test_health_and_models_expose_replaceable_adapters_and_license_flags():
    client = make_client()
    assert client.get("/health").json() == {"ok": True, "service": "mesh-api"}

    models = client.get("/v1/models").json()
    assert models["defaults"] == {"max_video_seconds": 120, "target_mesh_fps": 24}
    assert models["detectors"][0]["adapter"] == "mock-yolo"
    assert models["trackers"][0]["adapter"] == "mock-bytetrack"
    assert models["mesh_recoverers"][0]["adapter"] == "mock-humanoid-body"
    assert any(flag["commercial_use"] == "restricted" for flag in models["license_flags"])
    assert models["ingestors"][0]["adapter"] == "mock-video-ingestor"


def test_cors_allows_configured_vercel_frontend_origin():
    settings = Settings(max_video_seconds=120, target_mesh_fps=24, cors_origins=["https://stepwise.vercel.app"])
    client = TestClient(create_app(settings=settings))
    response = client.options(
        "/v1/models",
        headers={"Origin": "https://stepwise.vercel.app", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://stepwise.vercel.app"


def test_url_job_lifecycle_uses_api_probed_video_metadata_not_user_seconds():
    client = make_client("two_person_crossing")
    created = client.post("/v1/jobs", json={"source_url": "https://www.youtube.com/watch?v=stepwise-demo"}).json()
    assert created["stage"] == JobStage.QUEUED.value
    assert created["progress"] == 0

    status = client.get(f"/v1/jobs/{created['job_id']}").json()
    assert status["stage"] == JobStage.COMPLETE.value
    assert status["progress"] == 100
    assert status["people_detected"] == 2

    result = client.get(f"/v1/jobs/{created['job_id']}/result").json()
    assert result["video"]["source_url"] == "https://www.youtube.com/watch?v=stepwise-demo"
    assert result["video"]["duration_seconds"] == 2.0
    assert result["video"]["fps"] == 30
    assert result["video"]["dimensions"] == {"width": 1920, "height": 1080}
    assert result["schema_version"] == "mesh-result-v1"
    assert len(result["people"]) == 2
    assert {person["track_id"] for person in result["people"]} == {"person-alpha", "person-beta"}
    assert all(person["mesh_asset"] and person["mesh_asset"]["faces"] for person in result["people"])
    assert len(result["frames"]) >= 8
    assert result["analysis"]["difficulty"]["body_parts"]["arms"] > 0


def test_raw_uploaded_video_data_job_uses_api_owned_probe_and_pipeline():
    client = make_client("two_person_crossing")
    response = client.post(
        "/v1/jobs/upload",
        content=b"fake downloaded mp4 bytes",
        headers={"content-type": "video/mp4", "x-filename": "dance.mp4"},
    )
    assert response.status_code == 200
    job = response.json()
    status = client.get(f"/v1/jobs/{job['job_id']}").json()
    assert status["stage"] == "complete"

    result = client.get(f"/v1/jobs/{job['job_id']}/result").json()
    assert result["video"]["source_url"].startswith("storage://uploads/")
    assert result["video"]["duration_seconds"] == 2.0
    assert result["video"]["fps"] == 30
    assert result["video"]["dimensions"] == {"width": 1920, "height": 1080}
    assert result["people"][0]["mesh_asset"]["vertices"]


def test_presigned_upload_returns_cloudflare_r2_style_storage_reference():
    client = make_client("two_person_crossing")
    response = client.post(
        "/v1/uploads/presign",
        json={"filename": "dance practice.mp4", "content_type": "video/mp4", "content_length": 42},
    )

    assert response.status_code == 200
    presign = response.json()
    assert presign["method"] == "PUT"
    assert presign["upload_ref"].startswith("storage://uploads/")
    assert presign["object_key"].startswith("uploads/")
    assert presign["object_key"].endswith("/dance-practice.mp4")
    assert presign["headers"]["Content-Type"] == "video/mp4"
    assert presign["expires_in_seconds"] <= 900

    job = client.post("/v1/jobs", json={"upload_ref": presign["upload_ref"]}).json()
    assert client.get(f"/v1/jobs/{job['job_id']}").json()["stage"] == JobStage.COMPLETE.value


def test_upload_endpoint_persists_raw_video_and_completed_result_assets_to_storage():
    client = make_client("two_person_crossing")
    response = client.post(
        "/v1/jobs/upload",
        content=b"fake downloaded mp4 bytes",
        headers={"content-type": "video/mp4", "x-filename": "dance.mp4"},
    )

    assert response.status_code == 200
    store = client.app.state.object_storage
    job = response.json()
    stored_upload_keys = [key for key in store.objects if key.startswith("uploads/")]
    assert stored_upload_keys
    assert store.objects[stored_upload_keys[0]] == b"fake downloaded mp4 bytes"

    result = client.get(f"/v1/jobs/{job['job_id']}/result").json()
    result_key = f"results/{job['job_id']}/mesh-result-v1.json"
    assert result_key in store.objects
    assert result["assets"]["mesh_asset_urls"]
    assert all(asset["url"].startswith("memory://signed-get/") for asset in result["assets"]["mesh_asset_urls"])


def test_stylized_mock_mesh_is_humanoid_not_cuboid():
    client = make_client("two_person_crossing")
    job = client.post("/v1/jobs", json={"source_url": "https://www.tiktok.com/@demo/video/123"}).json()
    result = client.get(f"/v1/jobs/{job['job_id']}/result").json()
    mesh = result["people"][0]["mesh_asset"]

    assert mesh["source_model"] == "mock-stylized-humanoid-body"
    assert len(mesh["vertices"]) >= 120
    assert len(mesh["faces"]) >= 160
    joint_names = {joint["name"] for joint in mesh["joint_hierarchy"]}
    assert {"head", "neck", "chest", "left_upper_arm", "right_upper_arm", "left_thigh", "right_thigh"}.issubset(joint_names)

    xs = [vertex[0] for vertex in mesh["vertices"]]
    ys = [vertex[1] for vertex in mesh["vertices"]]
    zs = [vertex[2] for vertex in mesh["vertices"]]
    assert max(ys) - min(ys) > 1.4
    assert max(xs) - min(xs) > 0.75  # arms/shoulders extend beyond a torso box
    assert max(zs) - min(zs) > 0.16


def test_pipeline_keeps_track_ids_stable_through_crossing_occlusion():
    adapters = make_adapters("two_person_crossing")
    result = run_pipeline("https://example.com/two-person.mp4", Settings(), adapters)

    ids_by_frame = [tuple(person["track_id"] for person in frame.people) for frame in result.frames]
    assert all("person-alpha" in ids and "person-beta" in ids for ids in ids_by_frame[1:-1])
    alpha_positions = [person.global_transform.translation[0] for frame in result.frames for person in frame.people if person.track_id == "person-alpha"]
    beta_positions = [person.global_transform.translation[0] for frame in result.frames for person in frame.people if person.track_id == "person-beta"]
    assert alpha_positions[0] < alpha_positions[-1]
    assert beta_positions[0] > beta_positions[-1]


def test_mock_pipeline_animates_joints_for_actual_skinning_not_static_sliding_blob():
    result = run_pipeline("https://example.com/two-person.mp4", Settings(), make_adapters("two_person_crossing"))
    alpha_frames = [next(person for person in frame.people if person.track_id == "person-alpha") for frame in result.frames]
    first_left_hand = next(joint for joint in alpha_frames[0].joints_3d if joint.name == "left_hand")
    later_left_hand = next(joint for joint in alpha_frames[4].joints_3d if joint.name == "left_hand")
    first_left_foot = next(joint for joint in alpha_frames[0].joints_3d if joint.name == "left_foot")
    later_left_foot = next(joint for joint in alpha_frames[4].joints_3d if joint.name == "left_foot")

    assert first_left_hand.position != later_left_hand.position
    assert first_left_foot.position != later_left_foot.position
    assert later_left_hand.rotation != [0, 0, 0, 1]
    assert later_left_foot.rotation != [0, 0, 0, 1]

    mesh = result.people[0].mesh_asset
    assert mesh.inverse_bind_matrices[0] != [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def test_partial_mesh_failure_returns_successful_people_and_warning():
    client = make_client("partial_failure")
    job = client.post("/v1/jobs", json={"source_url": "https://example.com/group.mp4"}).json()
    result = client.get(f"/v1/jobs/{job['job_id']}/result").json()

    assert len(result["people"]) == 2
    failed = next(person for person in result["people"] if person["track_id"] == "person-gamma")
    ok = next(person for person in result["people"] if person["track_id"] == "person-alpha")
    assert failed["mesh_asset"] is None
    assert "mesh recovery failed" in failed["error"]
    assert ok["mesh_asset"]["vertices"]
    assert any("partial" in warning.lower() for warning in result["model_report"]["warnings"])


def test_invalid_url_video_too_long_no_people_and_adapter_unavailable_errors():
    client = make_client()
    invalid = client.post("/v1/jobs", json={"source_url": "ftp://example.com/file.mov"})
    assert invalid.status_code == 422

    too_long = make_client(max_seconds=1).post("/v1/jobs", json={"source_url": "https://example.com/long.mp4"})
    assert too_long.status_code == 400
    assert "too long" in too_long.json()["detail"].lower()

    no_people_client = make_client("no_people")
    job = no_people_client.post("/v1/jobs", json={"source_url": "https://example.com/empty.mp4"}).json()
    status = no_people_client.get(f"/v1/jobs/{job['job_id']}").json()
    assert status["stage"] == JobStage.FAILED.value
    assert "No people" in status["error"]

    unavailable = make_client(mesh_unavailable=True).post("/v1/jobs", json={"source_url": "https://example.com/dance.mp4"})
    assert unavailable.status_code == 503
    assert "mesh adapter unavailable" in unavailable.json()["detail"].lower()

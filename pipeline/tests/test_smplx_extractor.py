"""Tests for SMPL-X extraction (mock mode)."""

from __future__ import annotations

import pytest

from pipeline.services.smplx_extractor import extract_smplx, SmplxExtractionResult


class TestSmplxExtractionResult:
    def test_result_has_person_count(self):
        result = SmplxExtractionResult(person_count=2, person_poses=[])
        assert result.person_count == 2


class TestMockSmplxExtraction:
    @pytest.mark.asyncio
    async def test_returns_result(self):
        result = await extract_smplx(
            video_path="dummy.mp4",
            total_frames=30,
            fps=30.0,
        )
        assert result.person_count >= 1

    @pytest.mark.asyncio
    async def test_frame_count_matches(self):
        result = await extract_smplx(
            video_path="dummy.mp4",
            total_frames=60,
            fps=30.0,
        )
        # Each person should have total_frames entries
        person_0_frames = [p for p in result.person_poses if p.person_id == 0]
        assert len(person_0_frames) == 60

    @pytest.mark.asyncio
    async def test_params_have_correct_dimensions(self):
        result = await extract_smplx(
            video_path="dummy.mp4",
            total_frames=10,
            fps=30.0,
        )
        for person_pose in result.person_poses:
            p = person_pose.smplx_params
            assert len(p.betas) == 10
            assert len(p.body_pose) == 63
            assert len(p.left_hand_pose) == 45
            assert len(p.right_hand_pose) == 45
            assert len(p.global_orient) == 3
            assert len(p.transl) == 3

    @pytest.mark.asyncio
    async def test_person_ids_are_stable(self):
        result = await extract_smplx(
            video_path="dummy.mp4",
            total_frames=30,
            fps=30.0,
        )
        person_ids = {p.person_id for p in result.person_poses}
        # Mock generates 1-3 people; IDs should be sequential from 0
        assert 0 in person_ids

    @pytest.mark.asyncio
    async def test_timestamps_are_sequential(self):
        result = await extract_smplx(
            video_path="dummy.mp4",
            total_frames=30,
            fps=30.0,
        )
        person_0 = [p for p in result.person_poses if p.person_id == 0]
        timestamps = [p.timestamp for p in person_0]
        assert timestamps == sorted(timestamps)

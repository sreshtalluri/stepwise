# VRM Mannequin Model

Place `mannequin.vrm` in this directory.

For development, use any VRM model from:
- https://hub.vroid.com/ (free VRM models, check individual licenses)
- https://www.vroid.com/en/studio (create your own with VRoid Studio)

For production, create a custom holographic mannequin in Blender:
- Minimal geometric body (capsule limbs, sphere joints)
- Export as VRM using the VRM Add-on for Blender
- Must include full humanoid bone hierarchy + finger bones

The mannequin.vrm file is not committed to git (too large).
Add to .gitignore if needed.

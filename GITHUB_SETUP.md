# Publish and test via GitHub / HACS

This is a **beta**. Camera functionality has not been tested on every ONVIF model.
The GitHub repository must be **public** to work in HACS.

1. Create an empty public repository on GitHub, preferably named `onvif-camera-control`.
   Enable Issues, add a one-line Description, and add topics `home-assistant`, `hacs`, `onvif`, `camera`.
   Do not initialize it with a README or a license if you will push this directory using Git.
2. On your PC, extract this archive into a working directory.
3. GitHub metadata has already been configured for `l4r53n/onvif-camera-control` in `manifest.json`.
4. Check that the source contains **no credentials or private configuration**.
   This repository must not include HA `.storage` or credentials.
5. Publish the directory with Git (replace `l4r53n`):

   ```sh
   git init
   git branch -M main
   git add .
   git commit -m 'Initial ONVIF Camera Control beta'
   git remote add origin https://github.com/l4r53n/onvif-camera-control.git
   git push -u origin main
   ```

   GitHub CLI / SSH authentication can be used instead of HTTPS.
6. Open **Actions** on GitHub. The three checks are: HACS, Hassfest and offline tests.
   Correct any failures before creating your first GitHub release.
7. For beta testing, in Home Assistant open **HACS → ⋮ → Custom repositories**.
   Enter the repository URL and choose **Integration**. Install and restart Home Assistant.
   Then add **ONVIF Camera Control** from **Settings → Devices & services → Add integration**.
8. For live video, add the camera separately using Home Assistant's standard ONVIF integration.
9. HACS downloads only `custom_components/onvif_camera_control`. The dashboard generator
   is a separate script at `tools/generate_dashboard.py`. Follow the main README's instructions
   to generate and import the dashboard YAML. Dashboard YAML and `examples/` are **not** automatically installed by HACS.
10. After live testing, create a GitHub release such as `v0.2.0-beta.1`, or increment the integration version when code changes.

**Existing installation:** make a full HA backup before switching from manually installed files to a HACS-managed copy. Never remove its existing config entry without a backup; its entity IDs should be preserved by the component.

Automated CI tests do **not** verify that your physical camera accepts changed resolution, FPS, bitrate, or I-frame interval. That requires a controlled live test.

Read official docs: https://www.hacs.dev/docs/faq/custom_repositories/ and https://www.hacs.dev/docs/publish/integration/

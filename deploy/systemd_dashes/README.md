# SkyscraperHQ dashboard fleet — systemd units (2026-07-28)

Boot-persistent dashboards added in the 2026-07-28 session. These are the copies
of the live units under `/etc/systemd/system/`, kept in-repo so a disk swap or
re-clone can restore the boot wiring. All run `User=ross`, `Restart=always`/`on-failure`,
`WantedBy=multi-user.target`, bound `0.0.0.0`.

| Port | Unit | Tool | Purpose |
|------|------|------|---------|
| 8863 | qsb-agentic-traders-dash | tools/qsb_agentic_traders_dash.py | Live trading fleet (real broker truth) |
| 8864 | qsb-council-live-dash | tools/qsb_council_live_dash.py | Task Council train-track pipeline + Accept/Reject |
| 8870 | qsb-codex-floor-dash | tools/qsb_codex_floor_dash.py | Codex full-circle + terminal |
| 8871 | qsb-floor-planner-dash | tools/qsb_floor_directory_dash.py | Every floor · click to open |
| 8872 | qsb-tower-reorganizer | tools/qsb_tower_reorganizer.py | Guided floor moves (live apply) |
| 8873 | qsb-gene-pool-dash | tools/qsb_gene_pool_dash.py | Gene-pool controls / provider overrides |
| 8874 | qsb-floor53-command-dash | tools/qsb_floor53_command_dash.py | Floor 53 · whole-tower structure |
| 8875 | qsb-transit-map | tools/qsb_tower_transit_map.py | Underground — live tower-wide tube map |
| 8888 | qsb-control-hub | tools/qsb_control_hub.py | Single front door — links every dash |

Plus `qsb-task-council-autorunner.service.d/gene-verify.conf`: drop-in that sets
`COUNCIL_GENE_POOL_VERIFY=1`, `COUNCIL_MAX_CORRECTIONS=1`, `AUTORUNNER_INTERVAL=90`
so the autorunner verifies via gene-pool DeepSeek quorum when the `:9120` CEO
cockpits are down.

## Restore
```
sudo cp qsb-*.service /etc/systemd/system/
for d in *.service.d; do sudo mkdir -p /etc/systemd/system/$d && sudo cp $d/*.conf /etc/systemd/system/$d/; done
sudo cp qsb-task-council-autorunner.service.d/gene-verify.conf /etc/systemd/system/qsb-task-council-autorunner.service.d/
sudo systemctl daemon-reload
sudo systemctl enable --now qsb-transit-map qsb-control-hub qsb-council-live-dash qsb-codex-floor-dash \
  qsb-gene-pool-dash qsb-floor-planner-dash qsb-floor53-command-dash qsb-tower-reorganizer qsb-agentic-traders-dash
```

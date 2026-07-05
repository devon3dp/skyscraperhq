# QSB Tower V1

Penthouse reserved for future QSB Kernel 4.5 installation.

Run: ./setup.sh then ./run.sh
Open: http://127.0.0.1:8765



Model Infrastructure V1.1

Correct architectural separation:
- Floor 5: Coding Department. Consumer/workspace floor.
- Floor 23: AIR LLM Operations. External provider sockets.
- Floor 24: Model Routing Department. Routing exchange.
- Floor 27: Local Model Operations. Optional local model inventory.

Floor 5 does not directly access providers.
Coding requests travel as sealed packets to Floor 24 first.

Path:
Floor 5 -> Service Lift -> Floor 24 -> Model Lift -> Floor 27, Floor 23, or Roof

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/model_infrastructure_status.sh
./scripts/sync_ollama_inventory.sh
python3 scripts/route_model_request.py coding



Coding Department V1.1

Floor 5 is now a real coding workspace floor.

It includes:
- Claude Code Port
- Local Coder Port
- Coding request queue
- Patch queue
- Review queue
- Test queue
- Workspace registry
- Worker-slot registry
- Sealed handoff path to Floor 24 through the Service Lift

Floor 5 does not directly access providers.
All coding requests route to Floor 24 first.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/coding_department_status.sh
./scripts/seed_coding_department.sh
python3 scripts/create_coding_request.py "Build parser" code_generation "Prepare parser scaffold."



Model Routing Department V1.1

Floor 24 is now a routing exchange.

It includes:
- Sealed packet intake
- Provider selection simulation
- Route decision records
- Fallback route planning
- Model Lift handoff records
- Routing worker slots
- Dashboard panel

Floor 24 does not execute AI providers.
It only decides where sealed model-bound packets should go.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/process_model_routes.sh
./scripts/model_routing_status.sh
python3 tests/test_model_routing_department_v11.py



Local Model Operations Department V1.1

Floor 27 is now a local model inventory and readiness floor.

It includes:
- Optional Ollama model inventory
- Role classification
- Local model catalog
- Worker-slot recommendations
- Local model readiness records
- Dashboard panel

Floor 27 does not execute model inference yet.
It only inventories models and recommends future bindings.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/sync_local_model_inventory.sh
./scripts/local_model_operations_status.sh
python3 tests/test_local_model_operations_v11.py



AIR LLM Operations Department V1.1

Floor 23 is now an external provider socket layer.

It includes:
- AIR LLM Cloud socket
- Claude socket
- Claude Code handoff path
- OpenAI socket
- Gemini socket
- DeepSeek socket
- Future provider socket
- Provider health records
- Provider capability registry
- External handoff records
- Dashboard panel

Floor 23 does not execute provider calls.
External providers remain outside the building.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/refresh_provider_health.sh
./scripts/air_llm_operations_status.sh
python3 scripts/prepare_provider_handoff.py claude
python3 tests/test_air_llm_operations_v11.py



Adapter Systems Department V1.1

Floor 21 is now a neutral adapter socket layer.

It includes:
- Claude adapter socket
- Claude Code adapter socket
- Ollama adapter socket
- OpenAI adapter socket
- Gemini adapter socket
- DeepSeek adapter socket
- Local CLI adapter socket
- Filesystem adapter socket
- Future adapter socket
- Adapter health records
- Adapter capability registry
- Future handoff paths
- Dashboard panel

Floor 21 does not execute providers, CLI commands, or filesystem operations.
It only prepares neutral adapter sockets and bridge records.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/refresh_adapter_health.sh
./scripts/adapter_systems_status.sh
python3 scripts/prepare_adapter_handoff.py claude_adapter
python3 tests/test_adapter_systems_v11.py



Integration Services Department V1.1

Floor 22 is now the cross-floor service integration layer.

It includes:
- Integration registry
- Cross-floor service map
- Floor 5 -> Floor 21 -> Floor 24 path records
- Floor 24 -> Floor 27 / Floor 23 route records
- Provider integration readiness records
- Service dependency graph
- Integration health dashboard panel

Floor 22 does not execute providers, tools, adapters, CLI commands, file operations, or model calls.
It only coordinates service paths and readiness records.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/refresh_integration_health.sh
./scripts/integration_services_status.sh
python3 scripts/prepare_integration_handoff.py coding_to_adapter_to_routing
python3 tests/test_integration_services_v11.py



Diagnostics Department V1.1

Floor 33 is now the tower engineering inspection layer.

It includes:
- Full tower validation
- Registry validation
- Lift route validation
- Packet integrity validation
- Floor manifest validation
- Department module import checks
- Dashboard endpoint checks
- Model infrastructure checks
- Integration health checks
- Inspection reports
- Dashboard panel

Floor 33 does not execute providers, adapters, tools, CLI commands, file operations, models, or kernel logic.
It only inspects and reports.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/run_floor_33_diagnostics.sh
./scripts/diagnostics_department_status.sh
python3 tests/test_diagnostics_department_v11.py



Monitoring Department V1.1

Floor 34 is now the live building watch layer.

It includes:
- CPU/RAM/disk snapshot
- Dashboard heartbeat
- Dashboard process uptime tracker
- Lift traffic monitor
- Packet flow monitor
- Floor activity monitor
- Provider/socket watch
- Diagnostics summary watch
- Building health timeline
- Dashboard panel

Floor 34 does not execute providers, adapters, tools, CLI commands, model calls, or kernel logic.
It only watches and records live building activity.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/run_floor_34_monitoring.sh
./scripts/monitoring_department_status.sh
python3 tests/test_monitoring_department_v11.py



Infrastructure Services Department V1.1

Floor 35 is now the building operations and maintenance layer.

It includes:
- Startup/shutdown service registry
- Script registry
- Runtime file checks
- SQLite database checks
- Log directory checks
- Backup readiness
- Repair hook registry
- Maintenance hook registry
- Service-control dashboard panel

Floor 35 does not execute repair hooks, providers, adapters, models, CLI commands, or kernel logic.
It only records readiness and infrastructure status.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/run_floor_35_infrastructure.sh
./scripts/infrastructure_services_status.sh
python3 tests/test_infrastructure_services_v11.py



Penthouse Readiness V1.1

The Penthouse is now prepared as a future installation socket for QSB Kernel 4.5.

It includes:
- Kernel Installation Socket
- Kernel Discovery Interface
- Kernel Monitoring Interface
- Kernel Health Display
- Kernel Event Console
- Kernel Connection Ports
- Floor 53 to Penthouse handoff
- Emergency Stairwell route validation
- Security/Permissions pre-check
- Kernel occupancy acceptance report
- Dashboard panel showing: Reserved For Future QSB Kernel 4.5 Installation

This does not build or install the QSB Kernel.
Kernel installed remains false.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/run_penthouse_acceptance.sh
./scripts/penthouse_readiness_status.sh
python3 tests/test_penthouse_readiness_v11.py



Security Spine V1.1

Floors 28-32 are now registered as the Security Spine:

- Floor 28 Security Department
- Floor 29 Guardian Department
- Floor 30 Permissions Department
- Floor 31 Audit Department
- Floor 32 Compliance Department

This includes:
- Security gates
- Guardian readiness rules
- Permission roles
- Lift permission records
- Audit records
- Compliance rules
- Security spine validation
- Dashboard panel

Security Spine V1.1 does not enforce live blocking yet.
It does not execute providers, adapters, models, CLI commands, or kernel logic.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/run_security_spine_check.sh
./scripts/security_spine_status.sh
python3 tests/test_security_spine_v11.py



Expansion Planning Department V1.1

Floor 36 now manages vacant expansion-ready floors 41-45.

It includes:
- Vacant floor registry
- Activation readiness checks
- Future department allocation planner
- Expansion hooks for floors 41-45
- Capacity report
- Service/lift/utility confirmation
- Dashboard panel showing expansion-ready floors

Vacant floors are fully serviced and ready for future departments.
Floor 36 does not activate departments automatically.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/run_floor_36_expansion.sh
./scripts/expansion_planning_status.sh
python3 scripts/prepare_vacant_floor_activation.py floor_41
python3 tests/test_expansion_planning_v11.py



Executive Command Spine V1.1

Floors 46-53 are now registered as the Executive Command Spine:

- Floor 46 Executive Support
- Floor 47 Executive Operations
- Floor 48 Strategic Planning
- Floor 49 Resource Management
- Floor 50 Building Governance
- Floor 51 Executive Council
- Floor 52 Infrastructure Command
- Floor 53 Tower Command / Kernel Handoff Preparation

This includes:
- Executive floor manifests
- Command channels
- Strategic roadmap registry
- Resource capacity registry
- Building governance rules
- Executive council records
- Infrastructure command links
- Tower Command to Penthouse handoff preparation
- Executive lift route validation
- Dashboard panel

Executive Command Spine V1.1 does not build, install, run, or contain the QSB Kernel.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/run_executive_command_check.sh
./scripts/executive_command_status.sh
python3 tests/test_executive_command_v11.py



Animated Skyscraper Dashboard V1.2

The dashboard now renders the tower as a living animated skyscraper cockpit.

It includes:
- Animated 53-floor tower
- Roof and Penthouse visual layers
- Active floor glow
- Vacant expansion-ready floors
- Zone coloring
- Animated lift shafts and lift cars
- Lift traffic visualization
- Sealed packet traffic feed
- Penthouse readiness panel
- Executive Command Spine panel
- Security Spine panel
- Expansion Planning panel
- Infrastructure, Monitoring, and Diagnostics panels
- Model/provider infrastructure visibility

The dashboard still does not install or run the QSB Kernel.
Kernel installed remains false.

Commands:
cd /vaults/nvme0/qsb_tower_v1
python3 tests/test_animated_dashboard_v12.py
./scripts/animated_dashboard_status.sh
./restart.sh



Interactive Command Center Dashboard V1.3

The dashboard now includes:
- Click a floor to inspect that floor
- Click a lift shaft or lift list item to inspect lift route and packets
- Click a packet to inspect sealed packet details
- Animated packet trails between floors
- Better compact lift labels
- Floor status legend
- Mini-map / zone selector
- Penthouse readiness banner
- Vacant-floor activation preview
- Live activity feed at the bottom

The dashboard still does not install or run QSB Kernel 4.5.
Kernel installed remains false.

Commands:
cd /vaults/nvme0/qsb_tower_v1
python3 tests/test_interactive_dashboard_v13.py
./scripts/interactive_dashboard_status.sh
./restart.sh



Foundation Completeness Patch V1.3A

This patch resolves pre-worker structural gaps found during the Claude Code read-only audit.

Added:
- Safe blocked activation stubs for floor activation_hook references.
- Service manifests for B1, B2, B3, Ground Reception, and Roof AIR LLM Cloud.
- Floor manifests for Floors 37–40.
- Explicit Python package markers: src/__init__.py and src/tower/__init__.py.
- Foundation completeness validation module, script, and test.

Safety:
- Does not install QSB Kernel 4.5.
- Does not enable workers.
- Does not enable providers.
- Does not activate floors.
- Activation scripts intentionally exit with status 2.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/foundation_completeness_status.sh
python3 tests/test_foundation_completeness_v13a.py

Next recommended phase:
Floor 25 Worker Recruitment and Coordination Department V1.1



Floor 26 Model Evaluation Department V1.1

Floor 26 now evaluates candidate workers, local model pools, and external provider sockets.

Installed:
- src/tower/model_evaluation_department.py
- config/model_evaluation.yaml
- data/registries/model_evaluation_policy.json
- data/registries/model_evaluation_criteria.json
- data/registries/model_candidate_evaluations.json
- floors/floor_26_model_evaluation_department/floor_manifest.json
- scripts/model_evaluation_status.sh
- scripts/run_floor26_evaluation.sh
- tests/test_model_evaluation_department_v11.py
- tests/test_dashboard_floor26_v11.py
- dashboard Floor 26 panel

Safety:
- Static registry metadata only.
- No model calls.
- No provider calls.
- No worker execution.
- No autonomous dispatch.
- QSB Kernel 4.5 is not installed.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/model_evaluation_status.sh
./scripts/run_floor26_evaluation.sh
python3 tests/test_model_evaluation_department_v11.py
python3 tests/test_dashboard_floor26_v11.py



Floor 37 Simulation Labs V1.1

Floor 37 now provides safe dry-run simulation of candidate workers, model routing, sealed packets, Security Spine checks, and Emergency Stairwell fallback.

Installed:
- src/tower/simulation_labs.py
- config/simulation_labs.yaml
- data/registries/simulation_labs_policy.json
- data/registries/simulation_scenarios.json
- data/registries/simulation_labs_latest_runs.json
- floors/floor_37_simulation_labs/floor_manifest.json
- scripts/simulation_labs_status.sh
- scripts/run_floor37_simulations.sh
- tests/test_simulation_labs_v11.py
- tests/test_dashboard_floor37_v11.py
- dashboard Floor 37 panel

Safety:
- Dry-run only.
- No real lift packet writes.
- No model calls.
- No provider calls.
- No worker execution.
- No autonomous dispatch.
- QSB Kernel 4.5 is not installed.

Commands:
cd /vaults/nvme0/qsb_tower_v1
./scripts/simulation_labs_status.sh
./scripts/run_floor37_simulations.sh
python3 tests/test_simulation_labs_v11.py
python3 tests/test_dashboard_floor37_v11.py

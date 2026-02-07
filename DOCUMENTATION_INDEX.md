# Codetoreum Documentation Index

Complete guide to all project documentation - start here to navigate the docs.

## 📋 Quick Start for Contributors

1. **New to the project?** → Read `CLAUDE.md` first (project overview)
2. **Adding features?** → Read `documentation/01_design/02_high_level_arch.md` (architecture)
3. **Writing tests?** → Read `tests/simulation/README.md` (simulation framework)
4. **Working with ports?** → Read `documentation/01_design/ports/output/COMPREHENSIVE_PORTS_REFERENCE.md`

---

## 📁 Documentation Structure

```
/
├── CLAUDE.md                           ← START HERE: Project overview & constraints
├── DOCUMENTATION_INDEX.md              ← YOU ARE HERE
│
├── documentation/
│   ├── 01_design/
│   │   ├── 02_high_level_arch.md       ← Architecture & layers
│   │   ├── 03_implementation_plan.md    ← Feature implementation guide
│   │   ├── domains/                    ← Domain model specifications
│   │   ├── application_services/       ← Service design docs
│   │   ├── input_ports/                ← Inbound port specs
│   │   ├── output_ports/               ← LEGACY port specs (Gen 1)
│   │   ├── ports/output/
│   │   │   ├── NEW_INTERFACES_QUICK_REFERENCE.md ← 8 main vendor-agnostic ports
│   │   │   ├── COMPREHENSIVE_PORTS_REFERENCE.md  ← ALL 28+ port interfaces
│   │   │   ├── REPAIR_CYCLE_CONTRACT.md
│   │   │   └── (individual port specs)
│   │   ├── events/                     ← Domain event catalog
│   │   └── infrastructure/
│   │       ├── resilience_infrastructure_design.md ← Resilience patterns
│   │       ├── simulation_design.md    ← Simulation framework design
│   │       └── MOCK_ADAPTERS_REFERENCE.md ← 18 testing adapters
│   │
│   └── simulation_scenarios/
│       ├── README.md                   ← Overview of scenarios
│       ├── SCENARIOS_COMPLETE.md       ← Detailed specs for all 12 scenarios
│       ├── SCENARIO_06_DOCUMENTATION.md ← Deep dive into Scenario 06
│       └── SCENARIO_FORMAT.md          ← How to write new scenarios
│
└── tests/
    └── simulation/
        ├── README.md                   ← Simulation testing framework
        ├── SCENARIO_FORMAT.md          ← Scenario creation guide
        ├── conftest.py                 ← Pytest fixtures
        ├── helpers.py                  ← Test helper functions
        ├── test_scenarios.py           ← Scenario test suite
        └── scenarios/
            ├── scenario_01_simple_workflow.py
            ├── scenario_02_parallel_executions.py
            ├── scenario_03_review_cycle.py
            ├── scenario_04_execution_failure.py
            ├── scenario_05_complex_workflow.py
            ├── scenario_06_sdlc_pipeline.py
            ├── scenario_06_sdlc_pipeline_with_repair.py
            ├── scenario_07_repair_cycle.py
            ├── scenario_09_queue_position_ordering.py
            ├── scenario_10_agent_execution.py
            ├── scenario_10_conversational_modes.py
            └── scenario_12_container_recovery.py
```

---

## 🎯 Documentation by Topic

### Architecture & Design
- **High-Level Architecture**: `documentation/01_design/02_high_level_arch.md`
- **Implementation Plan**: `documentation/01_design/03_implementation_plan.md`
- **Domain Models**: `documentation/01_design/domains/`
- **Application Services**: `documentation/01_design/application_services/`

### Port Interfaces (Critical!)
- **Quick Reference (8 main ports)**: `documentation/01_design/ports/output/NEW_INTERFACES_QUICK_REFERENCE.md`
- **Complete Reference (28+ ports)**: `documentation/01_design/ports/output/COMPREHENSIVE_PORTS_REFERENCE.md` ⭐ **NEW**
- **Gen 1 Ports (Legacy)**: `documentation/01_design/output_ports/output_ports_inventory.md`
- **Individual Port Specs**: `documentation/01_design/ports/output/*.md` or `documentation/01_design/output_ports/*.md`

### Infrastructure & Observability
- **Resilience Patterns**: `documentation/01_design/infrastructure/resilience_infrastructure_design.md`
- **Event Sourcing**: `documentation/01_design/infrastructure/simulation_design.md`
- **Simulation Design**: `documentation/01_design/infrastructure/simulation_design.md`

### Testing & Simulation
- **Simulation Framework Overview**: `tests/simulation/README.md` ⭐
- **Scenario Writing Guide**: `tests/simulation/SCENARIO_FORMAT.md` ⭐
- **All Scenarios Documented**: `documentation/simulation_scenarios/SCENARIOS_COMPLETE.md` ⭐ **NEW**
  - Scenario 01: Simple Workflow
  - Scenario 02: Parallel Executions
  - Scenario 03: Review Cycle
  - Scenario 04: Execution Failure
  - Scenario 05: Complex Workflow
  - Scenario 06: SDLC Pipeline (detailed: `SCENARIO_06_DOCUMENTATION.md`)
  - Scenario 06b: SDLC with Repair
  - Scenario 07: Repair Cycle
  - Scenario 09: Queue Position Ordering
  - Scenario 10: Agent Execution
  - Scenario 10b: Conversational Modes
  - Scenario 12: Container Recovery

### Mock Adapters
- **Complete Reference**: `documentation/01_design/infrastructure/MOCK_ADAPTERS_REFERENCE.md` ⭐ **NEW**
  - MockLLMAdapter
  - MockBoardAdapter
  - MockReviewCycleAdapter
  - MockRepairCycleAdapter
  - MockContainerRecoveryAdapter
  - InMemoryEventStore, Storage, Repository
  - FakeContainerAdapter
  - And 10+ more...

### Domain Events
- **Event Catalog**: `documentation/01_design/events/`

---

## 🔄 Documentation Status

### Complete ✅
- Architecture & design (Gen 2)
- Port interfaces (Gen 2 vendor-agnostic ports)
- Simulation testing framework
- **NEW**: All 12 simulation scenarios (comprehensive specs)
- **NEW**: All 18+ mock adapters
- **NEW**: Complete port interface inventory (28+)
- CLAUDE.md with simulation infrastructure

### Fixed Issues ✅
- ✅ SimulationRunner API is properly documented
- ✅ YAML scenario documentation clarified (configuration only, not scenario logic)
- ✅ Simulation scenarios 07-12 now have design documentation
- ✅ All mock adapters documented with usage examples
- ✅ Port interface documentation consolidated (old + new)
- ✅ Gen 1 → Gen 2 migration guidance in comprehensive reference

---

## 🚀 Common Tasks & Where to Start

### "I'm building a new feature"
1. Review existing architecture: `02_high_level_arch.md`
2. Check if new ports needed: `ports/output/COMPREHENSIVE_PORTS_REFERENCE.md`
3. Implement with tests: `tests/simulation/README.md`
4. Update this index and relevant design docs

### "I need to write a test"
1. Read `tests/simulation/README.md` (framework overview)
2. Pick a predefined scenario: `documentation/simulation_scenarios/SCENARIOS_COMPLETE.md`
3. Create test: `tests/simulation/SCENARIO_FORMAT.md`
4. Run scenarios: `pytest tests/simulation/`

### "I'm integrating with a new system"
1. Check for existing port: `ports/output/COMPREHENSIVE_PORTS_REFERENCE.md`
2. Implement adapter for port interface
3. Write contract tests
4. Add simulation/mock implementation: `MOCK_ADAPTERS_REFERENCE.md`

### "I need to debug a workflow issue"
1. Check domain events: `documentation/01_design/events/`
2. Run simulation scenario: `documentation/simulation_scenarios/SCENARIOS_COMPLETE.md`
3. Review event trail using simulation helpers: `tests/simulation/README.md`

### "I'm new to the project"
1. Start here: `CLAUDE.md` (overview)
2. Understand architecture: `02_high_level_arch.md`
3. Learn about ports: `ports/output/NEW_INTERFACES_QUICK_REFERENCE.md`
4. Try simulation: `tests/simulation/README.md`

---

## 📊 Documentation Metrics

| Category | Count | Status |
|----------|-------|--------|
| Design Docs | 20+ | ✅ Complete |
| Port Interfaces | 28+ | ✅ Complete (just indexed) |
| Simulation Scenarios | 12 | ✅ Complete (just documented) |
| Mock Adapters | 18 | ✅ Complete (just documented) |
| Domain Models | 10+ | ✅ Complete |
| Application Services | 8+ | ✅ Complete |
| Infrastructure Patterns | 5+ | ✅ Complete |

---

## 🔍 Key Documentation Additions (This Issue)

This issue fixed documentation-code mismatches in 5 key areas:

### 1. **Port Interfaces** ⭐
**New File**: `documentation/01_design/ports/output/COMPREHENSIVE_PORTS_REFERENCE.md`
- Complete inventory of all 28+ output ports
- Previously, only 8 "new" ports and 12 "old" ports were documented
- Now: All ports mapped, dependencies clarified, usage examples provided
- Includes Gen 1 → Gen 2 migration guidance

### 2. **Simulation Scenarios** ⭐
**New File**: `documentation/simulation_scenarios/SCENARIOS_COMPLETE.md`
- All 12 scenarios now have complete specifications
- Previously: Scenarios 1-5 had brief descriptions, 07-12 had none
- Now: Detailed test coverage, metrics, assertions, and use cases
- Organized as reference guide with templates for new scenarios

### 3. **Mock Adapters** ⭐
**New File**: `documentation/01_design/infrastructure/MOCK_ADAPTERS_REFERENCE.md`
- Complete reference for all 18+ testing adapters
- Covers MockLLMAdapter, MockBoardAdapter, MockRepairCycleAdapter, etc.
- Previously: Only scattered implementation comments
- Now: Usage patterns, configuration, and best practices

### 4. **YAML Scenario Documentation** ✅
**Updated**: `tests/simulation/SCENARIO_FORMAT.md`
- Clarified that YAML is for configuration only (not scenario logic)
- Removed references to non-existent YAML scenario example files
- Corrected references to Python scenario files in `scenarios/` directory

### 5. **CLAUDE.md Enhancement** ✅
**Updated**: Main project README
- Added "Simulation Testing Infrastructure" section
- Documented SimulationRunner, SimulationConfig, SimulationClock
- Added references to 18 mock adapters, 12 scenarios, 28+ ports
- Enhanced documentation links for simulation-related resources

---

## 📝 Documentation Files Added/Modified

### New Files
1. `documentation/01_design/ports/output/COMPREHENSIVE_PORTS_REFERENCE.md` (460 lines)
2. `documentation/simulation_scenarios/SCENARIOS_COMPLETE.md` (620 lines)
3. `documentation/01_design/infrastructure/MOCK_ADAPTERS_REFERENCE.md` (580 lines)
4. `DOCUMENTATION_INDEX.md` (this file)

### Modified Files
1. `tests/simulation/SCENARIO_FORMAT.md` (clarified YAML documentation)
2. `tests/simulation/README.md` (no changes needed - already accurate)
3. `CLAUDE.md` (added simulation infrastructure section)

### Total New Documentation
- **~1,700 lines** of documentation added
- **Fixes for 5 major documentation gaps**
- **Complete inventory of 28+ ports, 12 scenarios, 18+ adapters**

---

## ✅ Validation Checklist

All documentation mismatches resolved:

- [x] SimulationRunner assertions methods documented and implemented
- [x] YAML scenario format clarified (config only, not scenario logic)
- [x] All simulation scenarios (01-12) have design specifications
- [x] Mock adapters documented with usage examples
- [x] Port interfaces consolidated (all 28+ now inventoried)
- [x] Gen 1 → Gen 2 migration guidance provided
- [x] CLAUDE.md updated with simulation infrastructure
- [x] Documentation index created for navigation

---

## 🔗 Quick Links

**For Architecture Decisions**:
- `documentation/01_design/02_high_level_arch.md`
- `documentation/01_design/03_implementation_plan.md`

**For Port/Interface Details**:
- `documentation/01_design/ports/output/COMPREHENSIVE_PORTS_REFERENCE.md` ← **START HERE for complete port info**
- `documentation/01_design/ports/output/NEW_INTERFACES_QUICK_REFERENCE.md` ← Quick ref for 8 main ports

**For Testing**:
- `tests/simulation/README.md` ← Framework overview
- `documentation/simulation_scenarios/SCENARIOS_COMPLETE.md` ← All 12 scenarios
- `tests/simulation/SCENARIO_FORMAT.md` ← How to write new tests

**For Implementation**:
- `documentation/01_design/infrastructure/MOCK_ADAPTERS_REFERENCE.md` ← Testing adapters
- `documentation/01_design/domains/` ← Domain models
- `documentation/01_design/application_services/` ← Services

---

## 💡 Tips for Using This Documentation

1. **Use the Quick Start section** above to find what you need
2. **Check the Documentation by Topic** for comprehensive lists
3. **Each doc file has cross-references** to related docs
4. **Search for `⭐ NEW`** to find recently added documentation
5. **Search for `✅ FIXED`** to see what was corrected this issue

---

## 📞 Questions?

If documentation is unclear or missing:
1. Check this index for relevant docs
2. Review CLAUDE.md for project constraints
3. Check the specific topic section above
4. If still unclear, file an issue with details

---

**Last Updated**: February 6, 2026
**Status**: All major documentation mismatches resolved ✅


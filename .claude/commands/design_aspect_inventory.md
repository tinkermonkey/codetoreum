# Design Aspect Inventory

## Read and Execute
.claude/commands/prime_documentation.md

**IMPORTANT:** the requested design aspect is $ARGUMENTS

## Task

You are working to build a library of detailed design documentation for this project.

The system architecture is documented at a high level in `documentation/01_design/02_high_level_arch.md`

Desired design changes are documented in `documentation/01_design/01_design_changes.md`

The legacy system that is being redesigned is documented in `documentation/00_legacy/`

Your task is to:
1. Create a concise inventory of the requested design aspect based on the provided design changes documentation.
  - The inventory should be stored in the appropriate inventory document in `documentation/01_design/{aspect}/{aspect}_inventory.md`.
  - For example, if the requested design aspect is "domains", the inventory should be stored in `documentation/01_design/domains/domains_inventory.md`.
  - Review the system architecture and design changes documentation, and then extract all relevant items related to the requested design aspect from the legacy documentation to ensure the inventory is comprehensive.
  - The inventory should be a complete list of all of the individual items in the provided aspect of the design. For example, if the requested design aspect is "domains", the inventory should be a list of all of the different domains in the design.
2. Once the inventory is complete, for each item in the inventory, create a detailed design document in the appropriate subfolder in `documentation/01_design/{aspect}/{item}_design.md`.
  - For example, if the requested design aspect is "domains" and one of the items in the inventory is "work item", the detailed design document should be stored in `documentation/01_design/domains/work_item_design.md` and should provide all relevant design details for that specific item.
  - The detailed design document should provide a comprehensive overview of the design for that item, including any relevant diagrams, data structures, algorithms, etc.

**IMPORTANT**: The legacy documentation defined what the system needs to do, the design changes documentation defined how the redesigned system should be different, and the system architecture documentation defines the overall structure of the redesigned system. The system architecture documentation may be incomplete or have items which are not needed, use it for the patterns and design guidance and not the details.
# codetoreum - Architecture Model

This is a Documentation Robotics architecture model.

## Structure

- `documentation-robotics/` - Main project directory
  - `model/` - The canonical architecture model (11 layers)
  - `specs/` - Generated specifications (ArchiMate, OpenAPI, etc.)
  - `projection-rules.yaml` - Cross-layer projection rules
- `.dr/` - Tool configuration and schemas

## Quick Start

View model layers:
```bash
dr list business
```

Add an element:
```bash
dr add business service --name "My Service"
```

Validate model:
```bash
dr validate
```

## Model Information

- **Project:** codetoreum
- **Version:** 1.0.0

For more information, see the Documentation Robotics documentation.

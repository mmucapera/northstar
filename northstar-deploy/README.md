# Fabric Multi-Customer Deployment System

## Project Overview
This project implements a centralized CI/CD system for deploying Microsoft Fabric items to multiple customer workspaces using the `fabric-cicd` library with Azure DevOps orchestration.

## Project Structure
```
fabric-deployment-project/
├── README.md                           # This file
├── pipelines/
│   ├── azure-pipeline.yml              # Main Azure DevOps pipeline
│   └── templates/
│       ├── deployment-stage.yml        # Reusable deployment stage template
│       └── validation-stage.yml        # Validation stage template
├── scripts/
│   ├── deployment/
│   │   ├── deploy_orchestrator.py      # Main deployment orchestration
│   │   ├── config_processor.py         # Configuration processing utilities
│   │   ├── validation.py               # Pre/post deployment validation
│   │   └── retry_handler.py            # Retry logic implementation
│   ├── auth/
│   │   └── auth_spn.py                 # Service Principal authentication
│   └── utils/
│       └── logger.py                   # Logging utilities
├── configurations/                     # Customer configurations root
│   ├── _templates/                     # Configuration templates
│   │   ├── customer-template/
│   │   │   ├── config.yml
│   │   │   ├── parameters/
│   │   │   │   ├── dev.yml
│   │   │   │   ├── test.yml
│   │   │   │   ├── uat.yml
│   │   │   │   └── prod.yml
│   │   │   └── overrides/
│   │   │       └── selective-deploy.yml
│   ├── customer-001/                   # Example customer
│   └── customer-002/                   # Another customer
├── repository/                         # Fabric items repository
│   └── versions/
│       ├── v1.0.0/
│       │   ├── Lakehouse/
│       │   ├── Notebook/
│       │   ├── DataPipeline/
│       │   ├── SemanticModel/
│       │   └── Report/
│       └── v2.0.0/
└── docs/
    ├── SETUP_GUIDE.md
    ├── DEVELOPER_GUIDE.md
    └── CUSTOMER_ONBOARDING.md
```

## Quick Start

### Prerequisites
- Python 3.9-3.12
- Azure DevOps Project with Service Connection
- Microsoft Fabric Service Principal with workspace admin rights
- fabric-cicd library installed (`pip install fabric-cicd`)

### Initial Setup

1. **Clone the repository**
```bash
git clone <your-repo-url>
cd fabric-deployment-project
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure Azure DevOps**
- Create variable groups: `fabric-deployment-vars`
- Add Service Principal credentials
- Configure pipeline permissions

4. **Create customer configuration**
- Copy template from `configurations/_templates/customer-template/`
- Update workspace IDs and parameters
- Commit to repository

## Key Components

### 1. Deployment Orchestrator (`scripts/deployment/deploy_orchestrator.py`)
- Reads customer configuration
- Implements deployment sequencing (REQ-008)
- Handles deployment modes (REQ-006)
- Manages retry logic (REQ-019)

### 2. Configuration Processor (`scripts/deployment/config_processor.py`)
- Processes YAML configurations
- Handles variable substitution
- Creates temporary configs for sequenced deployment

### 3. Validation Engine (`scripts/deployment/validation.py`)
- Pre-deployment validation (REQ-007)
- Post-deployment verification
- Workspace and capacity checks

### 4. Azure Pipeline (`pipelines/azure-pipeline.yml`)
- Manual triggers only (REQ-010)
- Approval gates for production (REQ-009)
- Multi-stage deployment

## Configuration Structure

### Customer Config (`config.yml`)
- **metadata**: Custom customer information (not fabric-cicd native)
- **core**: Native fabric-cicd configuration
- **deployment**: Custom orchestration settings
- **publish/unpublish**: Native fabric-cicd settings
- **features**: Required fabric-cicd feature flags
- **validation**: Custom validation rules

### Parameter Files (`parameters/*.yml`)
- **environment**: Custom metadata
- **find_replace**: Native fabric-cicd parameter substitution

## Deployment Modes

1. **Full Deployment** (REQ-006)
   - Deploys all items
   - Cleans up orphaned items
   - Full validation

2. **Incremental Deployment**
   - Deploys only changed items
   - No cleanup
   - Standard validation

3. **Selective Deployment** (REQ-020)
   - Deploy specific items only
   - Skip non-essential validation (REQ-021)
   - No cleanup (REQ-023)

## Requirements Traceability

| Requirement | Implementation |
|-------------|----------------|
| REQ-001 | Configurations folder structure |
| REQ-002 | Multiple environment configs per customer |
| REQ-003 | Workspace ID and version in config |
| REQ-004 | find_replace in parameter files |
| REQ-005 | YAML configuration format |
| REQ-006 | Three deployment modes in orchestrator |
| REQ-007 | Validation.py module |
| REQ-008 | deployment_sequence in config |
| REQ-009 | Azure DevOps approval gates |
| REQ-010 | Manual pipeline triggers |
| REQ-015 | fabric-cicd library usage |
| REQ-016 | Sequenced deployment |
| REQ-017 | Parameter replacement |
| REQ-019 | Retry logic implementation |

## Next Steps for Development Team

1. **Complete Python Scripts**
   - Implement deployment sequencing logic
   - Add retry mechanism with exponential backoff
   - Create validation functions using Fabric REST APIs

2. **Azure DevOps Pipeline**
   - Configure service connections
   - Set up variable groups
   - Implement approval gates

3. **Testing**
   - Unit tests for Python modules
   - Integration tests with test workspace
   - End-to-end deployment validation

4. **Documentation**
   - API documentation for custom modules
   - Troubleshooting guide
   - Performance optimization tips

## Support
Contact: support@example.com

## Interactive Deploy (Single Command)

From the repository root, run:

```bash
./deploy-interactive.ps1
```

Or from the northstar-deploy folder, run:

```bash
uv run fabric-deploy
```

The CLI will:
1. Show all configured targets from deploy/deploy_targets.yml
2. Ask which target to deploy
3. Ask whether to run publish only or publish + orphan cleanup
4. Execute the deployment immediately

Alternative (without script install):

```bash
python deploy/deploy_cli.py
```

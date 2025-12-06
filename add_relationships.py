import yaml
import os

# Path to the technology layer file that should contain relationships.
# Based on manifest, technology layer path is documentation-robotics/model/05_technology/
# But relationships might be in a specific file or any file in that folder.
# Let's check manifest.yaml to see if there is a specific file for relationships or if we can add it to nodes.yaml.

# Manifest says:
#   technology:
#     ...
#     files:
#     - nodes.yaml
#     - platforms.yaml
#     - systemsoftwares.yaml

# It doesn't list a relationships file.
# However, the schema allows "relationships" at the top level.
# I will create a new file `relationships.yaml` in `documentation-robotics/model/05_technology/`
# and add it to the manifest.

relationships_file = '/home/austinsand/workspace/orchestrator/codetoreum/documentation-robotics/model/05_technology/relationships.yaml'
manifest_file = '/home/austinsand/workspace/orchestrator/codetoreum/documentation-robotics/model/manifest.yaml'

# Read the relationships I prepared
with open('relationships.yaml', 'r') as f:
    new_relationships = yaml.safe_load(f)

# Write to the new file
with open(relationships_file, 'w') as f:
    yaml.dump(new_relationships, f)

print(f"Created {relationships_file}")

# Now update manifest to include this file
with open(manifest_file, 'r') as f:
    manifest = yaml.safe_load(f)

if 'relationships.yaml' not in manifest['layers']['technology']['files']:
    manifest['layers']['technology']['files'].append('relationships.yaml')
    with open(manifest_file, 'w') as f:
        yaml.dump(manifest, f)
    print(f"Updated manifest to include relationships.yaml")
else:
    print("Manifest already includes relationships.yaml")

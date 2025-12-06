import yaml

manifest_path = 'documentation-robotics/model/manifest.yaml'

with open(manifest_path, 'r') as f:
    manifest = yaml.safe_load(f)

# Add to application layer
if 'relationships.yaml' not in manifest['layers']['application']['files']:
    manifest['layers']['application']['files'].append('relationships.yaml')

# Remove from technology layer
if 'relationships.yaml' in manifest['layers']['technology']['files']:
    manifest['layers']['technology']['files'].remove('relationships.yaml')

with open(manifest_path, 'w') as f:
    yaml.dump(manifest, f, default_flow_style=False, sort_keys=True)

print("Updated manifest: moved relationships.yaml from technology to application layer.")

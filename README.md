# XCP-NG Template Generator

A Python-based tool for automating the creation of VM templates in XCP-NG using the Xen Orchestra API. This tool streamlines the process of downloading cloud images, configuring them, and converting them into ready-to-use VM templates.

## Why This Project?

This project was created to address a specific limitation in the XCP-NG ecosystem. While HashiCorp Packer has a provider for XCP-NG, it cannot be used to import existing VMDK disk images directly. This tool fills that gap by providing a streamlined workflow to:

1. Download cloud-init compatible images from distribution repositories
2. Convert them to the appropriate format
3. Import them into XCP-NG storage repositories
4. Create properly configured templates from these images

By automating this process, we eliminate the manual steps typically required when Packer isn't suitable for the task.

## Features

- Automated template creation from cloud images
- YAML-based configuration for easy template definition
- Concurrent template generation for efficiency
- Progress tracking with rich console output
- Support for Debian cloud images (expandable to other distributions)
- Automatic cleanup of old templates

## Requirements

- Python 3.8 or higher
- Access to a Xen Orchestra API endpoint
- XCP-NG server with available storage repositories
- Xen Orchestra API token

## Installation

1. Clone this repository:

```bash
git clone https://gitlab.com/sed-infra-pegasus/xcp-ng/xo-template-generator.git
cd xo-template-generator
```

2. Install the required Python packages:

```bash
pip install -r requirements.txt
```

## Configuration

The tool uses a YAML configuration file to define templates. Each template consists of:

- **Source configuration**: Details about the cloud image to download
- **Target configuration**: Settings for the resulting VM template

### Example Configuration

Create a `config.yml` file with the following structure:

```yaml
---
- template:
    source:
      distribution: debian
      architecture: amd64
      version: 12
      variant: genericcloud
    target:
      name: debian-12-genericcloud-amd64
      cpu: 1
      memory: 1
      network: "Pool-wide network associated with eth1"
      sr: "Local storage - srv3"

- template:
    source:
      distribution: debian
      architecture: amd64
      version: 11
      variant: genericcloud
    target:
      name: debian-11-genericcloud-amd64
      cpu: 1
      memory: 1
      network: "Pool-wide network associated with eth1"
      sr: "Local storage - srv2"
```

### Configuration Options

#### Source Configuration

| Field | Description | Required | Supported Values |
|-------|-------------|----------|-----------------|
| `distribution` | Linux distribution | Yes | `debian` (currently only Debian is supported) |
| `architecture` | CPU architecture | Yes | `amd64`, `arm64` |
| `version` | Distribution version | Yes | Integer version number (e.g., `11`, `12`) |
| `variant` | Image variant | Yes | `genericcloud` and other Debian cloud variants |

#### Target Configuration

| Field | Description | Required |
|-------|-------------|----------|
| `name` | Template name | Yes |
| `cpu` | Number of CPUs | Yes |
| `memory` | Memory in GB | Yes |
| `network` | XCP-NG network name to attach | Yes |
| `sr` | Storage repository name | Yes |

## Usage

### Authentication

You need to provide Xen Orchestra API credentials. You can specify them in two ways:

1. Environment variables:
```bash
export XOA_URL="https://your-xoa-instance.example.com"
export XOA_TOKEN="your-api-token"
```

2. Command-line options:
```bash
./main.py generate --xoa-url "https://your-xoa-instance.example.com" --xoa-token "your-api-token"
```

### Commands

#### Generating Templates

```bash
# Using default config.yml file
./main.py generate

# Using a custom configuration file
./main.py generate --config my-templates.yml 

# Setting concurrency (number of templates to process in parallel)
./main.py generate --concurrent 3

# Enable debug logging
./main.py generate --debug
```

#### Listing Existing Templates

```bash
./main.py list-templates
```

### Example Workflow

1. Configure your `config.yml` with desired templates
2. Export your Xen Orchestra API credentials:
```bash
export XOA_URL="https://your-xoa-instance.example.com"
export XOA_TOKEN="your-api-token"
```
3. Run the generator:
```bash
./main.py generate
```
4. Review the created templates using:
```bash
./main.py list-templates
```

## How It Works

The template generation process follows these steps:

1. **Image Preparation**: Downloads and converts the cloud image to VMDK format
2. **Resource Collection**: Gets required XCP-NG resources (storage, network, base template)
3. **Disk Import**: Imports the converted disk image to XCP-NG
4. **VM Creation**: Creates a new VM with specified parameters
5. **VM Configuration**: Attaches the imported disk and sets boot order
6. **Template Conversion**: Converts the VM into a template
7. **Cleanup**: Removes older versions of the same template

## Troubleshooting

### Common Issues

- **Template Not Found**: Ensure the base template exists in XCP-NG with the expected name format
- **Network/SR Not Found**: Verify the exact names of networks and storage repositories in XCP-NG
- **API Connection Failed**: Check your API URL and token are correct

### Debug Mode

Use the `--debug` flag to get more detailed logs:

```bash
./main.py generate --debug
```

## Extending

### Supporting New Distributions

Currently, only Debian is supported. To add support for other distributions:

1. Create a new service class similar to `DebianCloudImage`
2. Update the `SourceConfig` model to allow the new distribution
3. Modify the `TemplateGenerator._prepare_image` method to use the appropriate service

## Credits

This project was inspired by the blog post [Creating a Debian Cloud-Init Template in Xen Orchestra](https://mikansoro.org/blog/debian-cloud-init-xen-orchestra/) written by @mikansoro.
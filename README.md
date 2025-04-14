# XCP-NG Template Generator

A Python-based tool for automating the creation of VM templates in XCP-NG using the Xen Orchestra API. This tool streamlines the process of downloading cloud images, configuring them, and converting them into ready-to-use VM templates.

## Why This Project?

This project was created to address a specific limitation in the XCP-NG ecosystem. While Packer has a provider for XCP-NG, it cannot be used to import existing disk images directly. This tool fills that gap by providing a streamlined workflow to:

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
- `qemu-img` installed
- Access to a Xen Orchestra API endpoint
- Xen Orchestra API token
- XCP-NG server with available storage repositories

## Demo

![Template Generator Demo](assets/demo.gif)

## Installation

Install the required Python packages:

```sh
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
templates:
  debian12:
    source:
      distribution: debian
      architecture: amd64
      version: 12
      variant: genericcloud
      base_template: Debian Bookworm 12
    target:
      name: debian-12-genericcloud-amd64
      cpu: 1
      memory: 1
      network: "Pool-wide network associated with eth1"
      sr: "Local storage - srv3"

  debian11:
    source:
      distribution: debian
      architecture: amd64
      version: 11
      variant: genericcloud
      base_template: Debian Bullseye 11
    target:
      name: debian-11-genericcloud-amd64
      cpu: 1
      memory: 1
      network: "Pool-wide network associated with eth1"
      sr: "Local storage - srv2"

  ubuntu2404:
    source:
      distribution: ubuntu
      architecture: amd64
      version: 24.04.2
      variant: live-server
      base_template:  Ubuntu Noble Numbat 24.04
    target:
      name: ubuntu-24.04.2-live-server-amd64
      cpu: 1
      memory: 1
      network: "Pool-wide network associated with eth1"
      sr: "Local storage - srv2"
```

### Configuration Options

#### Source Configuration

| Field | Description | Required | Supported Values |
|-------|-------------|----------|-----------------|
| `distribution` | Linux distribution | Yes | `debian`, `ubuntu` |
| `architecture` | CPU architecture | Yes | `amd64`, `arm64` |
| `version` | Distribution version | Yes | Integer version number (e.g., `11`, `12`) |
| `variant` | Image variant | Yes | `genericcloud` and other Debian cloud variants |
| `base_template` | Name for the template in XCP-NG | Yes | Descriptive name (e.g., `Debian Bookworm 12`) || 

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
python3 main.py generate --xoa-url "https://your-xoa-instance.example.com" --xoa-token "your-api-token"
```

### Commands

#### Generating Templates

```bash
# Using default config.yml file
python3 main.py generate

# Using a custom configuration file
python3 main.py generate --config my-templates.yml 

# Using concurrency
python3 main.py generate --concurrency 4
```

#### Listing Existing Templates

```bash
./main.py list-templates
```

## How It Works

The template generation process follows these steps:

1. **Image Preparation**: Downloads and converts the cloud image to ISO format
2. **Resource Collection**: Gets required XCP-NG resources (storage, network, base template)
3. **Disk Import**: Imports the disk image to XCP-NG
4. **VM Creation**: Creates a new VM with specified parameters
5. **VM Configuration**: Attaches the imported disk and sets boot order
6. **Template Conversion**: Converts the VM into a template
7. **Cleanup**: Removes older versions of the same template

## Troubleshooting


### Verbosity Levels

The tool supports multiple verbosity levels to help with troubleshooting:

```bash
# Default level (WARNING)
python3 main.py generate

# Increased verbosity (INFO level)
python3 main.py -v generate

# Debug level (maximum verbosity)
python3 main.py -vv generate
```

You can use these verbosity flags with any command:

```bash
# List templates with debug output
./main.py -vv list-templates
```

The verbosity flag controls the detail level of log messages:
- Default: Only WARNING and above (errors and warnings)
- `-v`: INFO level and above (general progress information)
- `-vv`: DEBUG level (detailed diagnostic information)

## Extending

### Supporting New Distributions

Currently, the tool supports both Debian and Ubuntu distributions. To add support for additional distributions:

1. Create a new provider class that inherits from `BaseImageProvider` (`service/image_providers/base.py`):

```python
class AlpineImageProvider(BaseImageProvider):
  # Code to complete
```

2. Register your provider in the `IMAGE_PROVIDERS` dictionary:

```python
IMAGE_PROVIDERS = {
  "debian": DebianImageProvider,
  "ubuntu": UbuntuImageProvider,
  "alpine": AlpineImageProvider,  # Add your new provider here
}
```

## Credits

This project was inspired by the blog post [Creating a Debian Cloud-Init Template in Xen Orchestra](https://mikansoro.org/blog/debian-cloud-init-xen-orchestra/) written by @mikansoro.
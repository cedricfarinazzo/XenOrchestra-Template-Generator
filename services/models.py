from typing import Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict

from .image_providers import IMAGE_PROVIDERS


class SourceConfig(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    distribution: str = Field(description="The Linux distribution")
    architecture: Literal["amd64", "arm64"] = Field(description="The CPU architecture")
    version: str = Field(description="The distribution version number")
    variant: str = Field(
        description="The image variant (e.g. genericcloud or live-server)"
    )
    base_template: str = Field(description="The base template name to use")

    @field_validator("distribution")
    @classmethod
    def validate_distribution(cls, v):
        if v.lower() not in IMAGE_PROVIDERS:
            raise ValueError(
                f"Unsupported distribution: {v}. Supported distributions are: {', '.join(IMAGE_PROVIDERS.keys())}"
            )
        return v.lower()


class TargetConfig(BaseModel):
    name: str = Field(description="The name of the target template")
    cpu: int = Field(description="Number of CPUs", ge=1)
    memory: int = Field(description="Memory in GB", ge=1)
    network: str = Field(description="Network name to connect the VM to")
    sr: str = Field(description="Storage repository name")


class TemplateConfig(BaseModel):
    source: SourceConfig = Field(description="Source image configuration")
    target: TargetConfig = Field(description="Target VM configuration")


class TemplateList(BaseModel):
    templates: dict[str, TemplateConfig] = Field(
        description="A dictionary of templates with their configurations"
    )

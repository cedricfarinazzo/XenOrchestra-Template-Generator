from typing import Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator

class SourceConfig(BaseModel):
    distribution: Literal["debian"] = Field(description="The Linux distribution")
    architecture: Literal["amd64", "arm64"] = Field(description="The CPU architecture")
    version: int = Field(description="The distribution version number")
    variant: str = Field(description="The image variant (e.g. genericcloud)")

    @field_validator('distribution')
    @classmethod
    def validate_distribution(cls, v):
        if v.lower() != 'debian':
            raise ValueError('Currently only Debian distribution is supported')
        return v.lower()
    
    @field_validator('architecture')
    @classmethod
    def validate_architecture(cls, v):
        return v.lower()


class TargetConfig(BaseModel):
    name: str = Field(description="The name of the target template")
    cpu: int = Field(description="Number of CPUs", ge=1)
    memory: int = Field(description="Memory in GB", ge=1)
    network: str = Field(description="Network name to connect the VM to")
    sr: str = Field(description="Storage repository name")


class TemplateConfig(BaseModel):
    template: Dict[str, Any] = Field(description="Template configuration")
    
    @field_validator('template')
    @classmethod
    def validate_template(cls, v):
        if 'source' not in v or 'target' not in v:
            raise ValueError("Template must have both 'source' and 'target' sections")
        return v
    
    def get_source_config(self) -> SourceConfig:
        return SourceConfig(**self.template['source'])
    
    def get_target_config(self) -> TargetConfig:
        return TargetConfig(**self.template['target'])
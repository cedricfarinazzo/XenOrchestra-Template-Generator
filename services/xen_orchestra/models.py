from typing import Literal
from pydantic import BaseModel, Field, field_validator


# Pydantic models for API parameter validation
class VmCreateParams(BaseModel):
    name_label: str
    name_description: str
    template_id: str
    network_id: str
    cpus: int = Field(1, ge=1)
    memory: int = Field(1, ge=1)
    bootAfterCreate: bool = False
    tags: list[str] = []


class DiskAttachParams(BaseModel):
    vm_id: str
    vdi_id: str
    mode: Literal["RO", "RW"] = "RW"
    bootable: bool = True


class BootOrderParams(BaseModel):
    vm_id: str
    boot_order: str

    @field_validator("boot_order")
    def validate_boot_order(cls, v):
        allowed_chars = set("cdn")
        if not all(c in allowed_chars for c in v):
            raise ValueError("Boot order can only contain 'c', 'd', or 'n' characters")
        return v

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Any, Dict

@dataclass
class ProjectConfig:
    name: str
    version: str
    authors: List[str]
    dependencies: dict
    build: BuildConfig

@dataclass
class BuildConfig:
    c_compiler: str
    c_flags: List[str]
    output_dir: str

def _parse_toml_minimal(content: str) -> Dict[str, Any]:
    """
    A minimal, specialized TOML parser for Veritas configuration.
    Supports [sections], key = "string", key = ["list"], and key = number.
    """
    data = {}
    current_section = None
    
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        if line.startswith('[') and line.endswith(']'):
            current_section = line[1:-1].strip()
            data[current_section] = {}
            continue
        
        if '=' in line:
            key, val_str = line.split('=', 1)
            key = key.strip()
            val_str = val_str.strip()
            
            # Parse value
            if val_str.startswith('"') and val_str.endswith('"'):
                val = val_str[1:-1]
            elif val_str.startswith('[') and val_str.endswith(']'):
                # Simple list of strings
                inner = val_str[1:-1]
                val = [s.strip().strip('"').strip("'") for s in inner.split(',') if s.strip()]
            else:
                try:
                    val = int(val_str)
                except ValueError:
                    val = val_str # Fallback
            
            if current_section:
                data[current_section][key] = val
            else:
                data[key] = val
                
    return data

def load_config(path: str = "veritas.toml") -> ProjectConfig:
    if not os.path.exists(path):
        return ProjectConfig(
            name="unknown",
            version="0.0.0",
            authors=[],
            dependencies={},
            build=BuildConfig(c_compiler="gcc", c_flags=["-O3", "-Wall", "-lm"], output_dir="build")
        )

    with open(path, "r") as f:
        content = f.read()
        
    data = _parse_toml_minimal(content)

    pkg = data.get("package", {})
    build = data.get("build", {})

    return ProjectConfig(
        name=pkg.get("name", "unknown"),
        version=pkg.get("version", "0.0.0"),
        authors=pkg.get("authors", []),
        dependencies=data.get("dependencies", {}),
        build=BuildConfig(
            c_compiler=build.get("c_compiler", "gcc"),
            c_flags=build.get("c_flags", ["-O3", "-Wall", "-lm"]),
            output_dir=build.get("output_dir", "build")
        )
    )

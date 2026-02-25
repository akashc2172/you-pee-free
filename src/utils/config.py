"""
Configuration utility for loading project parameters and settings.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import yaml
from dataclasses import dataclass

@dataclass
class VariableConfig:
    name: str
    type: str  # 'continuous' or 'discrete'
    range: Tuple[float, float]
    default: float
    description: str

class ConfigLoader:
    """Load configuration from parameters.yaml."""
    
    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            # Default to repo_root/config/parameters.yaml
            root = Path(__file__).parent.parent.parent
            config_path = root / "config" / "parameters.yaml"
        
        if not config_path.exists():
             raise FileNotFoundError(f"Config file not found at {config_path}")
             
        with open(config_path, 'r') as f:
            self._raw = yaml.safe_load(f)
            
        self.design_vars = self._parse_design_vars()
        self.constraints = self._raw.get('constraints', {})
        self.sampling = self._raw.get('sampling', {})
        self.optimization = self._raw.get('optimization', {})
        
    def _parse_design_vars(self) -> Dict[str, VariableConfig]:
        """Parse design variables section."""
        vars_dict = {}
        raw_vars = self._raw.get('design_variables', {})
        
        for name, data in raw_vars.items():
            vars_dict[name] = VariableConfig(
                name=name,
                type=data['type'],
                range=tuple(data['range']),
                default=data['default'],
                description=data.get('description', '')
            )
        return vars_dict
    
    def get_parameter_names(self) -> List[str]:
        """Get list of all design variable names."""
        return list(self.design_vars.keys())
    
    def get_bounds_list(self) -> List[Tuple[float, float]]:
        """Get ordered list of (min, max) for all parameters."""
        return [self.design_vars[name].range for name in self.get_parameter_names()]

    def get_continuous_vars(self) -> List[str]:
        return [n for n, v in self.design_vars.items() if v.type == 'continuous']
        
    def get_discrete_vars(self) -> List[str]:
        return [n for n, v in self.design_vars.items() if v.type == 'discrete']

    def get_stl_export_config(self) -> Dict[str, Any]:
        """Get STL export defaults and quality profiles."""
        return self._raw.get("stl_export", {})

    def get_cad_postprocess_config(self) -> Dict[str, Any]:
        """Get CAD post-process behavior config."""
        return self._raw.get("cad_postprocess", {})

"""
Canonical COMSOL template and parser expectations used by smoke-run tooling.
"""

from __future__ import annotations

from typing import Any, Dict, List

TEMPLATE_CONTRACT_SCHEMA_VERSION = "comsol_template_contract_v1"
PARSER_EXPECTATIONS_VERSION = "comsol_parser_expectations_v1"

RESULTS_FILENAME_TEMPLATE = "{run_id}_results.csv"
REALIZED_GEOMETRY_FILENAME_TEMPLATE = "{run_id}_realized_geometry.csv"
LOG_FILENAME_TEMPLATE = "{run_id}.log"

RESULT_COLUMN_ALIASES: Dict[str, List[str]] = {
    "q_out": [
        "q_out",
        "q_total",
        "spf_out1_volumeflowrate",
        "outlet_volume_flow_rate",
    ],
    "q_in": [
        "q_in",
        "spf_inl1_volumeflowrate",
        "inlet_volume_flow_rate",
    ],
    "p_in": [
        "p_in",
        "p_inlet",
        "spf_inl1_paverage",
        "inlet_average_pressure",
    ],
    "p_out": [
        "p_out",
        "p_outlet",
        "spf_out1_paverage",
        "outlet_average_pressure",
    ],
    "delta_p": [
        "delta_p",
        "dp",
        "pressure_drop",
    ],
    "mass_imbalance": [
        "mass_imbalance",
        "mass_balance_error",
    ],
    "mesh_min_quality": [
        "minimum_element_quality",
        "mesh_min_quality",
        "min_element_quality",
    ],
    "solver_relative_tolerance": [
        "solver_relative_tolerance",
        "relative_tolerance",
        "solver_tol",
    ],
    "q_sh_prox": [
        "q_sh_prox",
        "q_sh_k",
        "proximal_side_hole_flow",
    ],
    "q_sh_mid": [
        "q_sh_mid",
        "q_sh_u",
        "middle_side_hole_flow",
    ],
    "q_sh_dist": [
        "q_sh_dist",
        "q_sh_b",
        "distal_side_hole_flow",
    ],
    "wss_max": [
        "wss_max",
        "max_wall_shear_stress",
        "spf_sr_max",
    ],
    "wss_p95_global": [
        "wss_p95_global",
        "wss_p95",
        "wall_shear_stress_p95",
    ],
    "wss_p99_global": [
        "wss_p99_global",
        "wss_p99",
        "wall_shear_stress_p99",
    ],
}

CONVERGENCE_LOG_PATTERNS: List[str] = [
    r"Stationary Solver.*Ended at",
    r"Solver finished\.",
    r"Study completed successfully",
]

TOLERANCE_LOG_PATTERNS: List[str] = [
    r"Relative tolerance(?:\s+used)?:?\s*([\d\.Ee+-]+)",
]

REQUIRED_TEMPLATE_CONTRACT_FIELDS = {
    "schema_version",
    "template_id",
    "template_version",
    "parser_expectations_version",
    "sim_contract_version",
    "domain_template",
    "selection_strategy",
    "pressure_contract",
    "required_named_selections",
    "required_exports",
    "artifact_filenames",
}

REQUIRED_NAMED_SELECTIONS = {
    "inlet",
    "outlet",
    "stent_walls",
    "coil_zone",
    "mid_zone",
}

# Recommended scientific-output selections for the baseline template.
# These are intentionally not hard-gated until the COMSOL template is rebuilt
# and smoke-tested with real hole-mouth selections.
RECOMMENDED_NAMED_SELECTIONS = {
    "sel_holes_prox",
    "sel_holes_mid",
    "sel_holes_dist",
    "sel_wall_global",
}

REQUIRED_EXPORTS = {
    "results_csv",
    "realized_geometry_csv",
}

ARTIFACT_FILENAME_TEMPLATES = {
    "results_csv": RESULTS_FILENAME_TEMPLATE,
    "realized_geometry_csv": REALIZED_GEOMETRY_FILENAME_TEMPLATE,
    "batch_log": LOG_FILENAME_TEMPLATE,
}

FLOW_SIGN_CONVENTION = {
    "q_in": "negative",
    "q_out": "positive",
}

PRESSURE_SIGN_CONVENTION = {
    "p_in": "greater_than_p_out",
    "delta_p": "positive",
}

DEFAULT_DELTA_P_ABS_TOLERANCE_PA = 1.0


def expected_artifact_names(run_id: str) -> Dict[str, str]:
    return {
        name: template.format(run_id=run_id)
        for name, template in ARTIFACT_FILENAME_TEMPLATES.items()
    }


def parser_expectations_snapshot(
    qc_thresholds: Dict[str, Any],
    expected_delta_p_pa: float | None,
) -> Dict[str, Any]:
    return {
        "parser_expectations_version": PARSER_EXPECTATIONS_VERSION,
        "result_column_aliases": RESULT_COLUMN_ALIASES,
        "recommended_named_selections": sorted(RECOMMENDED_NAMED_SELECTIONS),
        "convergence_log_patterns": CONVERGENCE_LOG_PATTERNS,
        "tolerance_log_patterns": TOLERANCE_LOG_PATTERNS,
        "required_realized_geometry_artifact": REALIZED_GEOMETRY_FILENAME_TEMPLATE,
        "required_results_artifact": RESULTS_FILENAME_TEMPLATE,
        "required_log_artifact": LOG_FILENAME_TEMPLATE,
        "delta_p_target_pa": expected_delta_p_pa,
        "delta_p_abs_tolerance_pa": qc_thresholds.get(
            "delta_p_abs_tolerance_pa",
            DEFAULT_DELTA_P_ABS_TOLERANCE_PA,
        ),
        "flow_sign_convention": FLOW_SIGN_CONVENTION,
        "pressure_sign_convention": PRESSURE_SIGN_CONVENTION,
    }

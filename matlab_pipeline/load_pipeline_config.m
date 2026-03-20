function config = load_pipeline_config(configFile)
%LOAD_PIPELINE_CONFIG Read and validate MATLAB COMSOL pipeline config.

if nargin ~= 1
    error('load_pipeline_config requires exactly one argument: configFile');
end

configPath = string(configFile);
if ~isfile(configPath)
    error('Pipeline config not found: %s', configPath);
end

raw = fileread(configPath);
config = jsondecode(raw);

requiredTopLevel = ["base_mph", "manifest_csv", "output_dir", "template"];
for i = 1:numel(requiredTopLevel)
    key = requiredTopLevel(i);
    if ~isfield(config, key)
        error('Pipeline config is missing required field: %s', key);
    end
end

config.base_mph = char(string(config.base_mph));
config.manifest_csv = char(string(config.manifest_csv));
config.output_dir = char(string(config.output_dir));

if ~isfile(config.base_mph)
    error('Configured base_mph does not exist: %s', config.base_mph);
end

if ~isfile(config.manifest_csv)
    error('Configured manifest_csv does not exist: %s', config.manifest_csv);
end

if ~isfield(config, 'execution')
    config.execution = struct();
end
config.execution = apply_default(config.execution, 'resume', true);
config.execution = apply_default(config.execution, 'continue_on_error', true);
config.execution = apply_default(config.execution, 'run_geometry_before_study', true);
config.execution = apply_default(config.execution, 'run_mesh_before_study', true);
config.execution = apply_default(config.execution, 'run_hole_flux_after_study', true);
config.execution = apply_default(config.execution, 'save_model_copy', true);
config.execution = apply_default(config.execution, 'copy_sidecar_flux_csv_into_attempt_dir', true);

if ~isfield(config, 'boundary_conditions')
    config.boundary_conditions = struct();
end
config.boundary_conditions = apply_default(config.boundary_conditions, 'p_inlet_pa', 490.0);
config.boundary_conditions = apply_default(config.boundary_conditions, 'p_outlet_pa', 0.0);
config.boundary_conditions = apply_default(config.boundary_conditions, 'delta_p_pa', 490.0);

if ~isfield(config, 'qc')
    config.qc = struct();
end
config.qc = apply_default(config.qc, 'expected_delta_p_pa', 490.0);
config.qc = apply_default(config.qc, 'delta_p_abs_tolerance_pa', 1.0);
config.qc = apply_default(config.qc, 'max_mass_balance_error', 0.01);
config.qc = apply_default(config.qc, 'min_mesh_quality', 0.05);
config.qc = apply_default(config.qc, 'max_solver_relative_tolerance', 1.0e-3);
config.qc = apply_default(config.qc, 'require_solver_tolerance', true);
config.qc = apply_default(config.qc, 'require_realized_geometry', true);
config.qc = apply_default(config.qc, 'require_convergence_evidence', true);

templateRequired = [
    "component_tag", "geometry_tag", "import_feature_tag", "study_tag", ...
    "method_call_tag", "results_export_tag", "realized_geometry_export_tag"
];
for i = 1:numel(templateRequired)
    key = templateRequired(i);
    if ~isfield(config.template, key)
        error('Pipeline config.template is missing required field: %s', key);
    end
end

config.template = apply_default(config.template, 'mesh_tag', '');
config.template = apply_default(config.template, 'hole_flux_input_mode', 'method_inputs');

if ~isfield(config.template, 'hole_flux_input_names')
    config.template.hole_flux_input_names = struct();
end
config.template.hole_flux_input_names = apply_default( ...
    config.template.hole_flux_input_names, 'hole_metadata_path', 'hole_metadata_path');
config.template.hole_flux_input_names = apply_default( ...
    config.template.hole_flux_input_names, 'design_id', 'design_id');

if ~isfield(config.template, 'parameter_names')
    config.template.parameter_names = struct();
end
config.template.parameter_names = apply_default(config.template.parameter_names, 'cad_path', 'cad_path');
config.template.parameter_names = apply_default(config.template.parameter_names, 'hole_metadata_path', 'hole_metadata_path');
config.template.parameter_names = apply_default(config.template.parameter_names, 'design_id', 'design_id');
config.template.parameter_names = apply_default(config.template.parameter_names, 'p_inlet_pa', 'p_inlet_pa');
config.template.parameter_names = apply_default(config.template.parameter_names, 'p_outlet_pa', 'p_outlet_pa');
config.template.parameter_names = apply_default(config.template.parameter_names, 'delta_p_pa', 'delta_p_pa');

if ~isfield(config, 'aliases')
    error('Pipeline config is missing aliases');
end
if ~isfield(config, 'log_patterns')
    error('Pipeline config is missing log_patterns');
end

if ~isfolder(config.output_dir)
    mkdir(config.output_dir);
end
end

function out = apply_default(in, fieldName, value)
out = in;
if ~isfield(out, fieldName)
    out.(fieldName) = value;
end
end

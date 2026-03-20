function record = run_one_shot_design(config, row)
%RUN_ONE_SHOT_DESIGN Execute one design through COMSOL from MATLAB.

designId = char(string(row.design_id));
cadFile = char(string(row.cad_file));
holeMetadataFile = char(string(row.hole_metadata_file));

runDir = fullfile(config.output_dir, designId);
attemptDir = fullfile(runDir, 'attempt_0');
if ~isfolder(attemptDir)
    mkdir(attemptDir);
end

matlabLog = fullfile(attemptDir, sprintf('%s_matlab.log', designId));
savedModelPath = fullfile(attemptDir, sprintf('%s.mph', designId));
resultsCsv = fullfile(attemptDir, sprintf('%s_results.csv', designId));
realizedCsv = fullfile(attemptDir, sprintf('%s_realized_geometry.csv', designId));
sidecarFluxCsv = fullfile(fileparts(holeMetadataFile), sprintf('%s_shaft_hole_flux.csv', designId));
attemptFluxCsv = fullfile(attemptDir, sprintf('%s_shaft_hole_flux.csv', designId));
resultJson = fullfile(runDir, sprintf('%s_result.json', designId));

record = struct( ...
    'design_id', designId, ...
    'cad_file', cadFile, ...
    'hole_metadata_file', holeMetadataFile, ...
    'run_dir', runDir, ...
    'attempt_dir', attemptDir, ...
    'run_status', "failed_setup", ...
    'failure_class', "failed_setup", ...
    'errors', "", ...
    'results_csv', resultsCsv, ...
    'realized_geometry_csv', realizedCsv, ...
    'shaft_hole_flux_csv', attemptFluxCsv, ...
    'saved_mph', savedModelPath, ...
    'matlab_log', matlabLog, ...
    'q_in', NaN, ...
    'q_out', NaN, ...
    'p_in', NaN, ...
    'p_out', NaN, ...
    'delta_p', NaN, ...
    'mass_imbalance', NaN, ...
    'mesh_min_quality', NaN, ...
    'solver_relative_tolerance', NaN, ...
    'convergence_evidence', false, ...
    'realized_geometry_present', false, ...
    'qc_passed', false);

errors = strings(0, 1);

if ~isfile(cadFile)
    errors(end + 1) = "cad_missing";
    record.errors = char(strjoin(errors, "; "));
    write_json(resultJson, record);
    return;
end

if ~isfile(holeMetadataFile)
    errors(end + 1) = "hole_metadata_missing";
    record.errors = char(strjoin(errors, "; "));
    write_json(resultJson, record);
    return;
end

diary(matlabLog);
cleanupDiary = onCleanup(@() diary('off'));

try
    import com.comsol.model.*
    import com.comsol.model.util.*

    ModelUtil.clear;
    model = mphopen(config.base_mph);
    cleanupModel = onCleanup(@() close_model(model));

    set_import_filename(model, config.template, cadFile);
    set_runtime_parameters(model, config, designId, cadFile, holeMetadataFile);

    if config.execution.run_geometry_before_study
        model.component(config.template.component_tag).geom(config.template.geometry_tag).run;
    end

    meshTag = char(string(config.template.mesh_tag));
    if config.execution.run_mesh_before_study && ~isempty(strtrim(meshTag))
        model.component(config.template.component_tag).mesh(meshTag).run;
    end

    model.study(config.template.study_tag).run;

    if config.execution.run_hole_flux_after_study
        apply_hole_flux_inputs(model, config.template, holeMetadataFile, designId);
        run_method_call(model, config.template.method_call_tag);
    end

    run_export(model, config.template.results_export_tag, resultsCsv);
    run_export(model, config.template.realized_geometry_export_tag, realizedCsv);

    if config.execution.save_model_copy
        mphsave(model, savedModelPath);
    end

    if config.execution.copy_sidecar_flux_csv_into_attempt_dir && isfile(sidecarFluxCsv)
        copyfile(sidecarFluxCsv, attemptFluxCsv);
    end

    metrics = parse_results_csv(resultsCsv, config.aliases);
    logInfo = parse_log(matlabLog, config.log_patterns);
    realizedPresent = parse_realized_geometry(realizedCsv);

    record.q_in = metrics.q_in;
    record.q_out = metrics.q_out;
    record.p_in = metrics.p_in;
    record.p_out = metrics.p_out;
    record.delta_p = metrics.delta_p;
    record.mass_imbalance = metrics.mass_imbalance;
    record.mesh_min_quality = metrics.mesh_min_quality;
    record.solver_relative_tolerance = pick_first_finite(metrics.solver_relative_tolerance, logInfo.solver_relative_tolerance);
    record.convergence_evidence = logInfo.convergence_evidence;
    record.realized_geometry_present = realizedPresent;

    [runStatus, failureClass, qcErrors] = apply_qc(record, config.qc);
    errors = [errors; string(metrics.errors(:)); string(logInfo.errors(:)); string(qcErrors(:))];

    if runStatus == "valid"
        record.qc_passed = true;
    end
    record.run_status = runStatus;
    record.failure_class = failureClass;
catch exc
    record.run_status = "failed_solver";
    record.failure_class = "matlab_exception";
    errors(end + 1) = "matlab_exception: " + string(exc.message);
end

record.errors = char(strjoin(errors(errors ~= ""), "; "));
write_json(resultJson, record);
end

function close_model(model)
try
    mphclose(model);
catch
end
end

function set_import_filename(model, template, cadFile)
model.component(template.component_tag) ...
    .geom(template.geometry_tag) ...
    .feature(template.import_feature_tag) ...
    .set('filename', cadFile);
end

function set_runtime_parameters(model, config, designId, cadFile, holeMetadataFile)
names = config.template.parameter_names;
model.param.set(names.cad_path, quote_string(cadFile));
model.param.set(names.design_id, quote_string(designId));
model.param.set(names.hole_metadata_path, quote_string(holeMetadataFile));
model.param.set(names.p_inlet_pa, sprintf('%.12g', config.boundary_conditions.p_inlet_pa));
model.param.set(names.p_outlet_pa, sprintf('%.12g', config.boundary_conditions.p_outlet_pa));
model.param.set(names.delta_p_pa, sprintf('%.12g', config.boundary_conditions.delta_p_pa));
end

function apply_hole_flux_inputs(model, template, holeMetadataFile, designId)
mode = string(template.hole_flux_input_mode);
if mode == "method_inputs"
    inputNames = template.hole_flux_input_names;
    set_method_call_input(model, template.method_call_tag, inputNames.hole_metadata_path, holeMetadataFile, 0);
    set_method_call_input(model, template.method_call_tag, inputNames.design_id, designId, 1);
elseif mode == "model_parameters"
    model.param.set(template.parameter_names.hole_metadata_path, quote_string(holeMetadataFile));
    model.param.set(template.parameter_names.design_id, quote_string(designId));
else
    error('Unsupported hole_flux_input_mode: %s', mode);
end
end

function set_method_call_input(model, methodCallTag, inputName, inputValue, inputIndex)
attempts = {
    @() model.methodCall(methodCallTag).set(inputName, inputValue), ...
    @() model.java.methodCall(methodCallTag).set(inputName, inputValue), ...
    @() model.methodCall(methodCallTag).setIndex('args', inputValue, inputIndex), ...
    @() model.java.methodCall(methodCallTag).setIndex('args', inputValue, inputIndex)
};

lastError = [];
for i = 1:numel(attempts)
    try
        attempts{i}();
        return;
    catch exc
        lastError = exc;
    end
end

if isempty(lastError)
    error('Could not set method call input %s on %s', inputName, methodCallTag);
else
    rethrow(lastError);
end
end

function run_method_call(model, methodCallTag)
attempts = {
    @() model.methodCall(methodCallTag).run(), ...
    @() model.java.methodCall(methodCallTag).run(), ...
    @() mphrun(model, {methodCallTag})
};

lastError = [];
for i = 1:numel(attempts)
    try
        attempts{i}();
        return;
    catch exc
        lastError = exc;
    end
end

if isempty(lastError)
    error('Could not run COMSOL method call tag: %s', methodCallTag);
else
    rethrow(lastError);
end
end

function run_export(model, exportTag, outputFile)
model.result.export(exportTag).set('filename', outputFile);
model.result.export(exportTag).run;
end

function metrics = parse_results_csv(filePath, aliases)
metrics = struct( ...
    'q_in', NaN, ...
    'q_out', NaN, ...
    'p_in', NaN, ...
    'p_out', NaN, ...
    'delta_p', NaN, ...
    'mass_imbalance', NaN, ...
    'mesh_min_quality', NaN, ...
    'solver_relative_tolerance', NaN, ...
    'errors', strings(0, 1));

if ~isfile(filePath)
    metrics.errors(end + 1) = "results_csv_missing";
    return;
end

tbl = readtable(filePath, 'VariableNamingRule', 'preserve');
if isempty(tbl)
    metrics.errors(end + 1) = "results_csv_empty";
    return;
end

row = tbl(end, :);
keys = containers.Map;
for i = 1:numel(row.Properties.VariableNames)
    original = row.Properties.VariableNames{i};
    normalized = normalize_key(original);
    value = row{1, i};
    if isnumeric(value)
        keys(normalized) = value;
    elseif iscell(value) && ~isempty(value) && isnumeric(value{1})
        keys(normalized) = value{1};
    else
        numericValue = str2double(string(value));
        if ~isnan(numericValue)
            keys(normalized) = numericValue;
        end
    end
end

metrics.q_out = lookup_alias(keys, aliases.q_out);
metrics.q_in = lookup_alias(keys, aliases.q_in);
metrics.p_in = lookup_alias(keys, aliases.p_in);
metrics.p_out = lookup_alias(keys, aliases.p_out);
metrics.delta_p = lookup_alias(keys, aliases.delta_p);
metrics.mass_imbalance = lookup_alias(keys, aliases.mass_imbalance);
metrics.mesh_min_quality = lookup_alias(keys, aliases.mesh_min_quality);
metrics.solver_relative_tolerance = lookup_alias(keys, aliases.solver_relative_tolerance);

if isnan(metrics.delta_p) && isfinite(metrics.p_in) && isfinite(metrics.p_out)
    metrics.delta_p = metrics.p_in - metrics.p_out;
end
end

function logInfo = parse_log(filePath, logPatterns)
logInfo = struct( ...
    'convergence_evidence', false, ...
    'solver_relative_tolerance', NaN, ...
    'errors', strings(0, 1));

if ~isfile(filePath)
    logInfo.errors(end + 1) = "matlab_log_missing";
    return;
end

text = fileread(filePath);
for i = 1:numel(logPatterns.convergence)
    if ~isempty(regexp(text, logPatterns.convergence{i}, 'once'))
        logInfo.convergence_evidence = true;
        break;
    end
end

for i = 1:numel(logPatterns.relative_tolerance)
    token = regexp(text, logPatterns.relative_tolerance{i}, 'tokens', 'once');
    if ~isempty(token)
        value = str2double(token{1});
        if isfinite(value)
            logInfo.solver_relative_tolerance = value;
            break;
        end
    end
end
end

function tf = parse_realized_geometry(filePath)
tf = false;
if ~isfile(filePath)
    return;
end

tbl = readtable(filePath, 'VariableNamingRule', 'preserve');
if isempty(tbl)
    return;
end

names = string(tbl.Properties.VariableNames);
tf = any(startsWith(lower(names), "realized_"));
end

function [runStatus, failureClass, errors] = apply_qc(record, qc)
errors = strings(0, 1);

if qc.require_convergence_evidence && ~record.convergence_evidence
    runStatus = "failed_solver";
    failureClass = "missing_convergence_evidence";
    errors(end + 1) = "missing_convergence_evidence";
    return;
end

required = [record.q_in, record.q_out, record.p_in, record.p_out, record.delta_p];
if any(~isfinite(required))
    runStatus = "failed_extraction";
    failureClass = "missing_required_outputs";
    errors(end + 1) = "missing_required_outputs";
    return;
end

if qc.require_realized_geometry && ~record.realized_geometry_present
    runStatus = "failed_extraction";
    failureClass = "missing_realized_geometry";
    errors(end + 1) = "missing_realized_geometry";
    return;
end

if qc.require_solver_tolerance && ~isfinite(record.solver_relative_tolerance)
    errors(end + 1) = "missing_solver_tolerance";
end

if isfinite(record.solver_relative_tolerance) && record.solver_relative_tolerance > qc.max_solver_relative_tolerance
    errors(end + 1) = "solver_tolerance_too_loose";
end

if abs(record.delta_p - qc.expected_delta_p_pa) > qc.delta_p_abs_tolerance_pa
    errors(end + 1) = "delta_p_mismatch";
end

if ~(record.p_in > record.p_out && record.delta_p > 0.0)
    errors(end + 1) = "pressure_sign_inconsistent";
end

if ~(record.q_in < 0.0 && record.q_out > 0.0)
    errors(end + 1) = "flow_sign_inconsistent";
end

massImbalance = record.mass_imbalance;
if ~isfinite(massImbalance)
    denom = max([abs(record.q_in), abs(record.q_out), 1.0e-15]);
    massImbalance = abs(record.q_in + record.q_out) / denom;
end
if massImbalance > qc.max_mass_balance_error
    errors(end + 1) = "mass_balance_too_high";
end

if isfinite(record.mesh_min_quality) && record.mesh_min_quality < qc.min_mesh_quality
    errors(end + 1) = "mesh_quality_below_threshold";
end

if isempty(errors)
    runStatus = "valid";
    failureClass = "";
else
    runStatus = "invalid_qc";
    failureClass = "invalid_qc";
end
end

function value = lookup_alias(mapObj, aliasList)
value = NaN;
for i = 1:numel(aliasList)
    key = normalize_key(aliasList{i});
    if isKey(mapObj, key)
        candidate = mapObj(key);
        if isnumeric(candidate) && isfinite(candidate)
            value = double(candidate);
            return;
        end
    end
end
end

function out = normalize_key(text)
out = lower(char(string(text)));
out = regexprep(out, '[^a-z0-9]+', '_');
out = regexprep(out, '^_+|_+$', '');
end

function out = quote_string(text)
escaped = strrep(char(string(text)), '"', '\"');
out = ['"' escaped '"'];
end

function value = pick_first_finite(a, b)
if isfinite(a)
    value = a;
elseif isfinite(b)
    value = b;
else
    value = NaN;
end
end

function write_json(path, payload)
text = jsonencode(payload, 'PrettyPrint', true);
fid = fopen(path, 'w');
if fid < 0
    error('Could not write JSON file: %s', path);
end
cleanup = onCleanup(@() fclose(fid));
fwrite(fid, text, 'char');
end

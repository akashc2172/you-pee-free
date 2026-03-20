function records = run_one_shot_campaign(configFile)
%RUN_ONE_SHOT_CAMPAIGN Run a full COMSOL campaign from MATLAB.

config = load_pipeline_config(configFile);
manifest = readtable(config.manifest_csv, 'TextType', 'string');

requiredColumns = ["design_id", "cad_file"];
for i = 1:numel(requiredColumns)
    if ~ismember(requiredColumns(i), manifest.Properties.VariableNames)
        error('Manifest is missing required column: %s', requiredColumns(i));
    end
end

if ~ismember("hole_metadata_file", manifest.Properties.VariableNames)
    holeMetadata = strings(height(manifest), 1);
    for i = 1:height(manifest)
        cadPath = string(manifest.cad_file(i));
        [folder, stem, ~] = fileparts(cadPath);
        holeMetadata(i) = fullfile(folder, stem + ".holes.json");
    end
    manifest.hole_metadata_file = holeMetadata;
end

outputDir = string(config.output_dir);
checkpointPath = fullfile(outputDir, 'batch_checkpoint.csv');
resultsPath = fullfile(outputDir, 'batch_results.csv');

done = containers.Map('KeyType', 'char', 'ValueType', 'logical');
records = struct([]);

if config.execution.resume && isfile(checkpointPath)
    existing = readtable(checkpointPath, 'TextType', 'string');
    if ~isempty(existing) && ismember("design_id", existing.Properties.VariableNames) ...
            && ismember("run_status", existing.Properties.VariableNames)
        records = table2struct(existing);
        terminal = ["valid", "invalid_qc", "failed_solver", "failed_extraction", "failed_setup"];
        for i = 1:height(existing)
            if any(existing.run_status(i) == terminal)
                done(char(existing.design_id(i))) = true;
            end
        end
    end
end

for i = 1:height(manifest)
    designId = char(string(manifest.design_id(i)));
    if isKey(done, designId)
        continue;
    end

    row = table2struct(manifest(i, :));
    record = run_one_shot_design(config, row);
    records = append_record(records, record);
    write_records(checkpointPath, records);

    if strcmp(record.run_status, 'valid') || config.execution.continue_on_error
        done(designId) = true;
    else
        done(designId) = true;
        break;
    end
end

write_records(resultsPath, records);
end

function out = append_record(records, record)
if isempty(records)
    out = record;
else
    out = [records; record];
end
end

function write_records(path, records)
if isempty(records)
    return;
end
tbl = struct2table(records, 'AsArray', true);
writetable(tbl, path);
end

# UML to JSON Schema Converter Workflow

This workflow automatically converts UML/XMI files to JSON Schema format and generates an OpenAPI specification. It's designed to work with the Gemeentelijk Gegevensmodel (GGM) project's version-based structure and serves as a method to get the objects ready for import in overige objecten or [open register](openregister.app).

## What it does

1. Monitors changes to the master branch
2. When changes are detected, it:
   - Processes XML/XMI files in version folders (e.g., v2.1.0)
   - Converts UML class definitions to JSON Schema format
   - Generates an OpenAPI specification that references all schemas
   - Saves the generated files in a `schemas` subfolder

## How it works

1. The workflow is triggered by pushes to the master branch
2. It ignores changes to schema files and markdown files to prevent infinite loops
3. The conversion process:
   - Reads XMI files from the version folder
   - Extracts UML class definitions
   - Converts them to JSON Schema format
   - Generates an OpenAPI specification
   - Saves all files in the schemas subfolder
4. The workflow has a 25-minute timeout to prevent infinite runs

## UML Tagged Values

The converter preserves UML tagged values using OpenAPI extensions (x- prefix) in the generated schemas:

1. Class-level tagged values:
   ```json
   {
     "type": "object",
     "title": "ExampleClass",
     "x-uml-tagged-value": {
       "stereotype": "BusinessObject",
       "author": "John Doe",
       "version": "1.0"
     }
   }
   ```

2. Property-level tagged values:
   ```json
   {
     "type": "object",
     "properties": {
       "exampleProperty": {
         "type": "string",
         "x-uml-tagged-value": {
           "stereotype": "Identifier",
           "format": "BSN",
           "required": "true"
         }
       }
     }
   }
   ```

This allows us to preserve important UML metadata in the generated schemas while maintaining compatibility with OpenAPI tools.

## Configuration

The workflow can be configured in two ways:

1. **Automatic Mode**: Without parameters, it processes all version folders
2. **Manual Mode**: With a specific version parameter, it only processes that version

### Manual Trigger

To manually trigger the workflow for a specific version:

1. Go to Actions tab in GitHub
2. Select "UML to JSON Schema Converter"
3. Click "Run workflow"
4. Enter the version folder name (e.g., "v2.1.0")

### File Structure

The workflow expects: 

project_root/
├── v2.1.0/
│ ├── some_uml_file.xml
│ └── schemas/ (generated)
│ ├── schemas/schema1.json
│ ├── schemas/schema2.json
│ └── schemas/openapi.json
├── v2.2.0/
│ └── ...
└── ...

## Output

The workflow generates:

1. JSON Schema files for each UML class
2. An OpenAPI specification referencing all schemas
3. All files are stored in a `schemas` subfolder within the version folder

## Error Handling

- The workflow will fail if no XML files are found
- It will skip invalid XML files
- It logs all conversions and errors
- If no changes are detected, the commit step is skipped
- The workflow will timeout after 25 minutes to prevent infinite runs

## Dependencies

- Python 3.10
- Required Python packages:
  - xmltodict
  - pyyaml
  - json-schema-generator
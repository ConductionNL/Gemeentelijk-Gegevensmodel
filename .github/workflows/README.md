# UML to JSON Schema Converter Workflow

This workflow automatically converts UML/XMI files to JSON Schema format and generates an OpenAPI specification. It's designed to work with the Gemeentelijk Gegevensmodel (GGM) project's version-based structure and serves as a method to get the objects ready for import in overige objecten or [open register](openregister.app).

## What it does

1. Monitors changes to the master branch
2. When changes are detected, it:
   - Processes XML/XMI files in version folders (e.g., v2.1.0)
   - Validates files are in XMI 2.1 format
   - Extracts UML class definitions and their attributes
   - Converts them to JSON Schema format
   - Generates an OpenAPI specification that references all schemas
   - Saves the generated files in a `schemas` subfolder

## XMI 2.1 Validation

The converter only processes files that conform to the XMI 2.1 specification. A file is considered valid if it:

1. Has an `xmi:XMI` root element
2. Contains the required XMI 2.1 namespaces:
   - `xmlns:xmi`
   - `xmlns:uml`
3. Contains a `uml:Model` element

Files that don't meet these criteria are skipped with a warning message.

## Filename Handling

The converter sanitizes class names when creating schema files to ensure valid filenames:

1. Replaces slashes and backslashes with underscores
2. Replaces spaces and special characters with underscores
3. Removes multiple consecutive underscores
4. Trims leading and trailing underscores
5. Converts to lowercase
6. Limits filename length to 100 characters
7. Uses 'unnamed' as fallback for empty names

Example transformations:
- "Deelplan/Veld" → "deelplan_veld"
- "Fase/Oplevering" → "fase_oplevering"
- "Gezinsmigrant en Overige migrant" → "gezinsmigrant_en_overige_migrant"

## UML Class Processing

The converter processes UML classes in the following way:

1. For each `UML:Class` element:
   ```xml
   <UML:Class name="ClassName" ...>
     <UML:ModelElement.taggedValue>
       <!-- Class-level tagged values -->
     </UML:ModelElement.taggedValue>
     <UML:Classifier.feature>
       <!-- Class attributes -->
     </UML:Classifier.feature>
   </UML:Class>
   ```

2. Extracts class information:
   - Name from `name` attribute
   - Documentation from tagged values
   - Class-level tagged values

3. For each attribute in `UML:Classifier.feature`:
   ```xml
   <UML:Attribute name="attributeName" ...>
     <UML:StructuralFeature.type>
       <!-- Attribute type -->
     </UML:StructuralFeature.type>
     <UML:ModelElement.taggedValue>
       <!-- Attribute-level tagged values -->
     </UML:ModelElement.taggedValue>
   </UML:Attribute>
   ```

4. Extracts attribute information:
   - Name from `name` attribute
   - Type from `UML:StructuralFeature.type`
   - Documentation and constraints from tagged values
   - Multiplicity from `lowerBound` and `upperBound` tagged values

5. Generates JSON Schema with:
   - Class name as title
   - Class documentation as description
   - Attributes as properties
   - Required fields based on multiplicity
   - Class and attribute tagged values as extensions

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
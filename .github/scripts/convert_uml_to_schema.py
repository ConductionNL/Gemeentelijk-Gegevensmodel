#!/usr/bin/env python3

"""
UML/XMI to JSON Schema Converter
This script converts UML class definitions from XMI files to JSON Schema format
and generates an OpenAPI specification that references all schemas.
"""

import os
import sys
import json
import xmltodict
from pathlib import Path
from typing import Dict, List, Optional

class UMLConverter:
    """Converts UML/XMI files to JSON Schema format"""
    
    def __init__(self, version_folder: str):
        self.version_folder = version_folder
        self.schemas: Dict[str, dict] = {}
        self.base_path = Path(version_folder)
        self.schema_path = self.base_path / 'schemas'  # Store schemas in schemas subfolder
        
    def process_xmi_file(self, file_path: Path) -> None:
        """Process an XMI file and convert it to JSON Schemas"""
        with open(file_path, 'r', encoding='utf-8') as f:
            xmi_data = xmltodict.parse(f.read())
            
        # Extract UML classes and convert them to JSON Schema
        uml_model = xmi_data.get('uml:Model', {})
        for package in uml_model.get('packagedElement', []):
            if package.get('@xmi:type') == 'uml:Package':
                self._process_package(package)
                
    def _process_package(self, package: dict) -> None:
        """Process a UML package and its classes"""
        for element in package.get('packagedElement', []):
            if element.get('@xmi:type') == 'uml:Class':
                schema = self._convert_class_to_schema(element)
                schema_name = element.get('@name', '').lower()
                self.schemas[schema_name] = schema
                
    def _convert_class_to_schema(self, uml_class: dict) -> dict:
        """Convert a UML class to JSON Schema format"""
        properties = {}
        required = []
        
        for attribute in uml_class.get('ownedAttribute', []):
            prop_name = attribute.get('@name', '')
            prop_type = attribute.get('type', {}).get('@href', 'string')
            
            # Map UML types to JSON Schema types
            json_type = self._map_type(prop_type)
            
            properties[prop_name] = {
                "type": json_type
            }
            
            if attribute.get('@multiplicity', '1') == '1':
                required.append(prop_name)
                
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": properties,
            "required": required
        }
        
    def _map_type(self, uml_type: str) -> str:
        """Map UML types to JSON Schema types"""
        type_mapping = {
            'string': 'string',
            'integer': 'integer',
            'boolean': 'boolean',
            'double': 'number',
            'date': 'string',
            'datetime': 'string'
        }
        return type_mapping.get(uml_type.lower(), 'string')
        
    def generate_openapi_spec(self) -> dict:
        """Generate OpenAPI specification referencing all schemas"""
        return {
            "openapi": "3.0.0",
            "info": {
                "title": "GGM API Specification",
                "version": self.version_folder.replace('v', '')
            },
            "paths": {},
            "components": {
                "schemas": {
                    name: {"$ref": f"./schemas/{name}.json"}
                    for name in self.schemas.keys()
                }
            }
        }
        
    def save_schemas(self) -> None:
        """Save all generated schemas and OpenAPI spec to files"""
        # Create schemas directory if it doesn't exist
        self.schema_path.mkdir(parents=True, exist_ok=True)
        
        # Save individual schemas
        for name, schema in self.schemas.items():
            schema_file = self.schema_path / f"{name}.json"
            with open(schema_file, 'w', encoding='utf-8') as f:
                json.dump(schema, f, indent=2)
                
        # Save OpenAPI spec
        oas_file = self.schema_path / "openapi.json"
        with open(oas_file, 'w', encoding='utf-8') as f:
            json.dump(self.generate_openapi_spec(), f, indent=2)

def main():
    """Main entry point"""
    version = sys.argv[1] if len(sys.argv) > 1 else None
    
    if version:
        versions = [version]
    else:
        # Find all version folders
        versions = [d for d in os.listdir('.') if d.startswith('v')]
        
    for version in versions:
        converter = UMLConverter(version)
        xmi_files = list(Path(version).glob('*.xml'))
        
        for xmi_file in xmi_files:
            converter.process_xmi_file(xmi_file)
            
        converter.save_schemas()

if __name__ == "__main__":
    main() 
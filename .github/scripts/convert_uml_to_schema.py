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
import chardet
from tqdm import tqdm

class UMLConverter:
    """Converts UML/XMI files to JSON Schema format"""
    
    def __init__(self, version_folder: str):
        self.version_folder = version_folder
        self.schemas: Dict[str, dict] = {}
        self.base_path = Path(version_folder)
        self.schema_path = self.base_path / 'schemas'  # Store schemas in schemas subfolder
        
    def detect_encoding(self, file_path: Path) -> str:
        """Detect the encoding of a file"""
        with open(file_path, 'rb') as f:
            raw_data = f.read()
            result = chardet.detect(raw_data)
            print(f"Detected encoding: {result}")
            # Try common encodings first
            common_encodings = ['utf-8', 'utf-16', 'iso-8859-1', 'windows-1252']
            if result['encoding'] and result['confidence'] > 0.7:
                return result['encoding']
            return 'utf-8'  # Default to UTF-8
        
    def read_file_with_encoding(self, file_path: Path) -> str:
        """Read file content with fallback encodings"""
        encodings = ['utf-8', 'utf-16', 'iso-8859-1', 'windows-1252']
        last_error = None
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError as e:
                last_error = e
                continue
                
        if last_error:
            raise last_error
            
        raise ValueError(f"Could not read file {file_path} with any of the encodings: {encodings}")
        
    def count_packages(self, xmi_data: dict) -> int:
        """Count the total number of packages in the XMI data"""
        count = 0
        uml_model = xmi_data.get('uml:Model', {})
        for package in uml_model.get('packagedElement', []):
            if package.get('@xmi:type') == 'uml:Package':
                count += 1
                # Count nested packages
                count += self._count_nested_packages(package)
        return count
    
    def _count_nested_packages(self, package: dict) -> int:
        """Count nested packages recursively"""
        count = 0
        for element in package.get('packagedElement', []):
            if element.get('@xmi:type') == 'uml:Package':
                count += 1
                count += self._count_nested_packages(element)
        return count
        
    def process_xmi_file(self, file_path: Path) -> None:
        """Process an XMI file and convert it to JSON Schemas"""
        try:
            print(f"\nProcessing file: {file_path}")
            print(f"File size: {file_path.stat().st_size / 1024 / 1024:.2f} MB")
            
            # Read file content with fallback encodings
            content = self.read_file_with_encoding(file_path)
            print("Successfully read file content")
            
            # Parse XML
            xmi_data = xmltodict.parse(content)
            print("Successfully parsed XML")
                
            # Count total packages for progress bar
            total_packages = self.count_packages(xmi_data)
            print(f"Found {total_packages} packages to process")
                
            # Extract UML classes and convert them to JSON Schema
            uml_model = xmi_data.get('uml:Model', {})
            with tqdm(total=total_packages, desc="Processing packages") as pbar:
                for package in uml_model.get('packagedElement', []):
                    if package.get('@xmi:type') == 'uml:Package':
                        self._process_package(package, pbar)
                    
        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            raise
                
    def _process_package(self, package: dict, pbar: tqdm) -> None:
        """Process a UML package and its classes"""
        # Process classes in this package
        for element in package.get('packagedElement', []):
            if element.get('@xmi:type') == 'uml:Class':
                schema = self._convert_class_to_schema(element)
                schema_name = element.get('@name', '').lower()
                self.schemas[schema_name] = schema
                
        # Process nested packages
        for element in package.get('packagedElement', []):
            if element.get('@xmi:type') == 'uml:Package':
                self._process_package(element, pbar)
                
        pbar.update(1)
                
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
        print(f"\nCreated schemas directory: {self.schema_path}")
        
        # Save individual schemas with progress bar
        print(f"\nSaving {len(self.schemas)} schemas...")
        for name, schema in tqdm(self.schemas.items(), desc="Saving schemas"):
            schema_file = self.schema_path / f"{name}.json"
            with open(schema_file, 'w', encoding='utf-8') as f:
                json.dump(schema, f, indent=2)
                
        # Save OpenAPI spec
        print("Saving OpenAPI specification...")
        oas_file = self.schema_path / "openapi.json"
        with open(oas_file, 'w', encoding='utf-8') as f:
            json.dump(self.generate_openapi_spec(), f, indent=2)
        print(f"Saved OpenAPI spec to: {oas_file}")

def main():
    """Main entry point"""
    version = sys.argv[1] if len(sys.argv) > 1 else None
    
    if version:
        versions = [version]
    else:
        # Find all version folders
        versions = [d for d in os.listdir('.') if d.startswith('v')]
        
    for version in versions:
        print(f"\nProcessing version: {version}")
        converter = UMLConverter(version)
        xmi_files = list(Path(version).glob('*.xml'))
        
        if not xmi_files:
            print(f"No XML files found in {version}")
            continue
            
        print(f"Found {len(xmi_files)} XML files")
        
        for xmi_file in xmi_files:
            converter.process_xmi_file(xmi_file)
            
        converter.save_schemas()
        print(f"\nSaved schemas to {version}/schemas/")

if __name__ == "__main__":
    main() 
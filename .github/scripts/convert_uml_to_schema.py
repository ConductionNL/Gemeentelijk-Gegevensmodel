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
from typing import Dict, Any, Optional, List, Union
import chardet
from tqdm import tqdm
import yaml
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(levelname)s - %(message)s')

class UMLConverter:
    """
    Converts UML/XMI files to JSON Schema format.
    
    This class handles the conversion of Enterprise Architect UML exports to JSON Schema,
    specifically designed for the Gemeentelijk Gegevensmodel (GGM) project.
    """

    def __init__(self, version_folder: str):
        """
        Initialize the UML converter.

        Args:
            version_folder (str): Path to the version folder containing UML files
        """
        self.version_folder = Path(version_folder)
        self.schemas: Dict[str, dict] = {}
        self.schema_folder = self.version_folder / 'schemas'
        self.schema_folder.mkdir(exist_ok=True)

    def detect_encoding(self, file_path: Path) -> str:
        """
        Detect the encoding of a file.

        Args:
            file_path (Path): Path to the file

        Returns:
            str: Detected encoding
        """
        with open(file_path, 'rb') as file:
            raw_data = file.read()
            result = chardet.detect(raw_data)
            return result['encoding'] or 'windows-1252'  # Default to windows-1252 for EA files

    def read_file_with_encoding(self, file_path: Path) -> str:
        """
        Read a file with proper encoding detection.

        Args:
            file_path (Path): Path to the file

        Returns:
            str: File contents
        """
        encoding = self.detect_encoding(file_path)
        try:
            with open(file_path, 'r', encoding=encoding) as file:
                return file.read()
        except UnicodeDecodeError:
            # Fallback to windows-1252 if specified in the XML
            with open(file_path, 'r', encoding='windows-1252') as file:
                return file.read()

    def process_xmi_file(self, file_path: Path) -> None:
        """
        Process an XMI file and convert its contents to JSON Schema.

        Args:
            file_path (Path): Path to the XMI file
        """
        logging.info(f"Processing file: {file_path}")
        
        try:
            # Read and parse XMI file
            content = self.read_file_with_encoding(file_path)
            xmi_data = xmltodict.parse(content)
            
            if 'xmi:XMI' in xmi_data:
                model = xmi_data['xmi:XMI'].get('uml:Model', {})
                if model and 'packagedElement' in model:
                    self._process_package_elements(model['packagedElement'])
                    
        except Exception as e:
            logging.error(f"Error processing file {file_path}: {str(e)}")
            raise

    def _process_package_elements(self, elements: Union[dict, list]) -> None:
        """
        Process package elements from the UML model.

        Args:
            elements: Package elements to process (dict or list)
        """
        if not elements:
            return
            
        # Convert single element to list for consistent processing
        if not isinstance(elements, list):
            elements = [elements]
            
        for element in elements:
            element_type = element.get('@xmi:type', '')
            
            if element_type == 'uml:Package':
                # Process nested packages
                if 'packagedElement' in element:
                    self._process_package_elements(element['packagedElement'])
                    
            elif element_type == 'uml:Class':
                # Convert class to schema
                schema = self._convert_class_to_schema(element)
                name = element.get('@name', 'Unknown')
                if name != 'Unknown':
                    self.schemas[name] = schema
                    logging.info(f"Generated schema for class: {name}")
                    
            elif element_type == 'uml:Component':
                # Handle components as classes if they have attributes
                if 'ownedAttribute' in element:
                    schema = self._convert_class_to_schema(element)
                    name = element.get('@name', 'Unknown')
                    if name != 'Unknown':
                        self.schemas[name] = schema
                        logging.info(f"Generated schema for component: {name}")

    def _convert_class_to_schema(self, uml_class: dict) -> dict:
        """
        Convert a UML class to JSON Schema format.

        Args:
            uml_class (dict): UML class data

        Returns:
            dict: JSON Schema representation
        """
        name = uml_class.get('@name', 'Unknown')
        properties = {}
        required = []
        
        # Basic schema structure
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "title": name,
            "description": f"Generated from UML {uml_class.get('@xmi:type', 'class')} {name}",
            "properties": properties,
            "required": required
        }
        
        # Process attributes
        if 'ownedAttribute' in uml_class:
            attrs = uml_class['ownedAttribute']
            if not isinstance(attrs, list):
                attrs = [attrs]
                
            for attr in attrs:
                # Skip association ends
                if 'association' in attr:
                    continue
                    
                attr_name = attr.get('@name', '')
                if not attr_name:
                    continue
                    
                # Get type information
                type_info = attr.get('type', {})
                type_href = type_info.get('@href', '')
                type_name = type_info.get('@name', 'string')
                
                # Map UML type to JSON Schema type
                json_type = self._map_type(type_name)
                
                # Create property definition
                prop_def = {
                    "type": json_type,
                    "description": f"UML attribute {attr_name}"
                }
                
                # Add property
                properties[attr_name] = prop_def
                
                # Check if property is required
                if attr.get('@lowerBound', '0') != '0':
                    required.append(attr_name)
        
        return schema

    def _map_type(self, uml_type: str) -> str:
        """
        Map UML types to JSON Schema types.

        Args:
            uml_type (str): UML type name

        Returns:
            str: Corresponding JSON Schema type
        """
        type_mapping = {
            'string': 'string',
            'integer': 'integer',
            'int': 'integer',
            'boolean': 'boolean',
            'double': 'number',
            'float': 'number',
            'date': 'string',
            'datetime': 'string',
            'time': 'string',
            'char': 'string',
            'text': 'string'
        }
        
        return type_mapping.get(uml_type.lower(), 'string')

    def generate_openapi_spec(self) -> dict:
        """
        Generate OpenAPI specification from the converted schemas.

        Returns:
            dict: OpenAPI specification
        """
        spec = {
            "openapi": "3.0.0",
            "info": {
                "title": "Gemeentelijk Gegevensmodel API",
                "version": self.version_folder.name.replace('v', ''),
                "description": "Generated from UML models"
            },
            "paths": {},
            "components": {
                "schemas": self.schemas
            }
        }
        
        return spec

    def save_schemas(self) -> None:
        """
        Save all generated schemas and OpenAPI specification to files.
        """
        # Save individual schemas
        for name, schema in self.schemas.items():
            schema_file = self.schema_folder / f"{name.lower()}.json"
            with open(schema_file, 'w', encoding='utf-8') as f:
                json.dump(schema, f, indent=2, ensure_ascii=False)
                
        # Save OpenAPI spec
        openapi_spec = self.generate_openapi_spec()
        openapi_file = self.schema_folder / "openapi.json"
        with open(openapi_file, 'w', encoding='utf-8') as f:
            json.dump(openapi_spec, f, indent=2, ensure_ascii=False)
            
        logging.info(f"Saved {len(self.schemas)} schemas and OpenAPI specification")

def main():
    """
    Main entry point for the UML to JSON Schema converter.
    """
    # Get version folder from command line argument or use default
    version_folder = sys.argv[1] if len(sys.argv) > 1 else "v2.1.0"
    
    try:
        converter = UMLConverter(version_folder)
        
        # Process all XML files in the version folder
        xml_files = list(Path(version_folder).glob("*.xml"))
        if not xml_files:
            logging.error(f"No XML files found in {version_folder}")
            sys.exit(1)
            
        for xml_file in xml_files:
            converter.process_xmi_file(xml_file)
            
        converter.save_schemas()
        logging.info("Conversion completed successfully")
        
    except Exception as e:
        logging.error(f"Conversion failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 
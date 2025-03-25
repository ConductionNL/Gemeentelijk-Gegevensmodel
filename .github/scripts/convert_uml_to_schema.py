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
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Tuple
import logging
from tqdm import tqdm

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(levelname)s - %(message)s')

class UMLConverter:
    """
    Converts UML/XMI files to JSON Schema format.
    
    This class handles the conversion of Enterprise Architect UML exports to JSON Schema,
    specifically designed for the Gemeentelijk Gegevensmodel (GGM) project.
    Only processes valid XMI 2.1 files.
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

    def _is_valid_xmi_2_1(self, xmi_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if the file is a valid XMI 2.1 file.
        
        Args:
            xmi_data: Parsed XML data
            
        Returns:
            Tuple of (is_valid, reason)
        """
        # Check for XMI root element
        if 'xmi:XMI' not in xmi_data:
            return False, "Missing XMI root element"
            
        xmi = xmi_data['xmi:XMI']
        
        # Check for required XMI 2.1 namespaces
        required_ns = ['xmi', 'uml']
        for ns in required_ns:
            if f'@xmlns:{ns}' not in xmi:
                return False, f"Missing required namespace: {ns}"
                
        # Check for UML model
        if 'uml:Model' not in xmi:
            return False, "Missing UML model element"
            
        return True, "Valid XMI 2.1 file"

    def _sanitize_filename(self, name: str) -> str:
        """
        Sanitize a string to be used as a filename.
        
        Args:
            name (str): The original filename
            
        Returns:
            str: A sanitized version of the filename that is safe to use
        """
        # Replace various special characters with underscores
        sanitized = re.sub(r'[/\\?*"|<>:\n\r]', '_', name)
        # Replace spaces with hyphens
        sanitized = re.sub(r'\s+', '-', sanitized)
        # Remove any other non-alphanumeric characters except hyphens and underscores
        sanitized = re.sub(r'[^a-zA-Z0-9\-_]', '', sanitized)
        # Ensure the filename is not empty
        if not sanitized:
            sanitized = "unnamed"
        return sanitized

    def _get_tagged_values(self, element: Dict[str, Any]) -> Dict[str, str]:
        """
        Extract tagged values from a UML element.
        
        Args:
            element: Dictionary containing the UML element
            
        Returns:
            Dictionary of tagged values
        """
        tagged_values = {}
        
        # Handle both single and multiple tagged values
        if 'properties' in element:
            props = element['properties']
            if isinstance(props, dict):
                for key, value in props.items():
                    if key not in ['isSpecification', 'sType', 'nType', 'scope']:
                        tagged_values[key] = str(value)
                        
        return tagged_values

    def _get_attribute_type(self, attribute: Dict[str, Any]) -> str:
        """
        Get the type of a UML attribute.
        
        Args:
            attribute: Dictionary containing the UML attribute
            
        Returns:
            The attribute type as a string
        """
        if 'type' in attribute:
            type_elem = attribute['type']
            if isinstance(type_elem, dict):
                return type_elem.get('@xmi:idref', 'string')
        return 'string'

    def _is_required(self, attribute: Dict[str, Any]) -> bool:
        """
        Check if an attribute is required.
        
        Args:
            attribute: Dictionary containing the UML attribute
            
        Returns:
            bool: True if the attribute is required, False otherwise
        """
        # Check if explicitly marked as required
        is_required = attribute.get('@isRequired', 'false').lower() == 'true'
        
        # Check lower bound
        lower = attribute.get('@lower', '0')
        if lower.isdigit() and int(lower) > 0:
            is_required = True
        
        return is_required

    def _create_property_definition(self, attribute: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a JSON Schema property definition from a UML attribute.
        
        Args:
            attribute: Dictionary containing the UML attribute
            
        Returns:
            A JSON Schema property definition
        """
        # Get attribute name and type
        name = attribute.get('@name', '')
        type_name = self._get_attribute_type(attribute)
        
        # Get tagged values for documentation and constraints
        tagged_values = self._get_tagged_values(attribute)
        
        # Create property definition
        prop_def = {
            'description': tagged_values.get('documentation', f'Property {name}'),
            'type': 'string'  # Default type
        }
        
        # Add format based on type name
        type_name = type_name.lower()
        if 'date' in type_name and 'time' not in type_name:
            prop_def['format'] = 'date'
        elif 'datetime' in type_name or 'timestamp' in type_name:
            prop_def['format'] = 'date-time'
        elif 'email' in type_name:
            prop_def['format'] = 'email'
        elif 'uri' in type_name:
            prop_def['format'] = 'uri'
        elif 'bsn' in type_name:
            prop_def['pattern'] = '^[0-9]{9}$'
        elif 'postcode' in type_name:
            prop_def['pattern'] = '^[1-9][0-9]{3}[A-Z]{2}$'
        elif type_name in ('integer', 'int'):
            prop_def['type'] = 'integer'
        elif type_name in ('double', 'float', 'decimal'):
            prop_def['type'] = 'number'
        elif type_name == 'boolean':
            prop_def['type'] = 'boolean'
        
        # Handle multiplicity
        is_required = attribute.get('@isRequired', 'false').lower() == 'true'
        lower = attribute.get('@lower', '0')
        upper = attribute.get('@upper', '1')
        
        if upper == '*' or (upper.isdigit() and int(upper) > 1):
            return {
                'type': 'array',
                'items': prop_def,
                'minItems': int(lower) if lower.isdigit() else 0
            }
        
        return prop_def

    def _convert_class_to_schema(self, uml_class: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        Convert a UML class to a JSON Schema.
        
        Args:
            uml_class: The UML class element to convert
            
        Returns:
            A tuple of (class name, JSON Schema dict)
        """
        # Clean the class name by removing HTML special characters and extra whitespace
        class_name = uml_class.get('@name', '').strip()
        # Remove HTML special characters like &#xA; (newline), &#xD; (carriage return), etc.
        class_name = re.sub(r'&#x[A-F0-9]+;', '', class_name, flags=re.IGNORECASE)
        class_name = re.sub(r'&[a-z]+;', '', class_name, flags=re.IGNORECASE)
        # Clean up any remaining whitespace
        class_name = re.sub(r'\s+', ' ', class_name)
        
        # Create the schema
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "title": class_name,
            "description": f"Schema for {class_name}",
            "properties": {},
            "required": [],
            "metadata": {
                "labels": ["schemas"]
            }
        }
        
        # Process attributes
        attributes = uml_class.get('ownedAttribute', [])
        if not isinstance(attributes, list):
            attributes = [attributes]
        
        for attr in attributes:
            if isinstance(attr, dict):
                property_name = attr.get('@name', '')
                if property_name:
                    property_def = self._create_property_definition(attr)
                    schema['properties'][property_name] = property_def
                    if self._is_required(attr):
                        schema['required'].append(property_name)
        
        # Add tagged values as metadata
        tagged_values = self._get_tagged_values(uml_class)
        if tagged_values:
            schema['metadata'].update(tagged_values)
        
        return class_name, schema

    def process_xmi_file(self, file_path: Path) -> None:
        """
        Process an XMI file and generate JSON Schema files.
        Only processes valid XMI 2.1 files.
        
        Args:
            file_path: Path to the XMI file
        """
        try:
            # Read and parse the file
            with open(file_path, 'r', encoding='windows-1252') as f:
                content = f.read()
            
            # Parse XML to dictionary
            xmi_data = xmltodict.parse(content)
            
            # Validate XMI 2.1
            is_valid, reason = self._is_valid_xmi_2_1(xmi_data)
            if not is_valid:
                logging.warning(f"Skipping {file_path}: {reason}")
                return
            
            # Find all UML classes
            classes = []
            if 'xmi:XMI' in xmi_data:
                model = xmi_data['xmi:XMI'].get('uml:Model', {})
                if model:
                    # Process all packages recursively
                    def process_package(pkg):
                        elements = []
                        if 'packagedElement' in pkg:
                            pkg_elements = pkg['packagedElement']
                            if not isinstance(pkg_elements, list):
                                pkg_elements = [pkg_elements]
                            
                            for elem in pkg_elements:
                                if elem.get('@xmi:type') == 'uml:Class':
                                    elements.append(elem)
                                elif elem.get('@xmi:type') == 'uml:Package':
                                    elements.extend(process_package(elem))
                        return elements
                    
                    classes = process_package(model)
            
            # Process each class
            for class_elem in classes:
                try:
                    name, schema = self._convert_class_to_schema(class_elem)
                    
                    # Sanitize filename
                    safe_name = self._sanitize_filename(name)
                    
                    # Save schema to file
                    schema_file = self.schema_folder / f"{safe_name}.json"
                    with open(schema_file, 'w', encoding='utf-8') as f:
                        json.dump(schema, f, indent=2, ensure_ascii=False)
                        
                    self.schemas[name] = schema
                    logging.info(f"Generated schema for class: {name}")
                except Exception as e:
                    class_name = class_elem.get('@name', 'Unknown')
                    logging.error(f"Error processing class {class_name}: {str(e)}")
                    
        except Exception as e:
            logging.error(f"Error processing file {file_path}: {str(e)}")

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
    # Get version folder from command line argument
    if len(sys.argv) > 1:
        version_folder = sys.argv[1]
    else:
        logging.error("No version folder specified")
        sys.exit(1)
    
    try:
        converter = UMLConverter(version_folder)
        
        # Process all XML files in the version folder
        xml_files = list(Path(version_folder).glob("*.xml"))
        if not xml_files:
            logging.error(f"No XML files found in {version_folder}")
            sys.exit(1)
        
        # Create progress bar for files
        with tqdm(total=len(xml_files), desc="Processing files", unit="file") as pbar:
            for xml_file in xml_files:
                try:
                    converter.process_xmi_file(xml_file)
                except Exception as e:
                    logging.error(f"Failed to process {xml_file}: {str(e)}")
                finally:
                    pbar.update(1)
            
        converter.save_schemas()
        logging.info("Conversion completed successfully")
        
    except Exception as e:
        logging.error(f"Conversion failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 
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
        Sanitize a filename by replacing invalid characters.
        
        Args:
            name: The original filename
            
        Returns:
            A sanitized filename that is valid on all operating systems
        """
        # Replace newlines and other whitespace with underscores
        name = re.sub(r'\s+', '_', name)
        
        # Replace slashes and backslashes with underscores
        name = re.sub(r'[/\\]', '_', name)
        
        # Replace any other special characters with underscores
        name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
        
        # Remove multiple consecutive underscores
        name = re.sub(r'_+', '_', name)
        
        # Trim leading and trailing underscores
        name = name.strip('_')
        
        # Convert to lowercase
        name = name.lower()
        
        # Limit length to 100 characters
        name = name[:100]
        
        # Use 'unnamed' as fallback for empty names
        if not name:
            name = 'unnamed'
            
        return name

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

    def _convert_class_to_schema(self, class_elem: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a UML class to a JSON Schema.
        
        Args:
            class_elem: Dictionary containing the UML class
            
        Returns:
            A JSON Schema representation of the class
        """
        # Get class name and documentation
        name = class_elem.get('@name', '')
        tagged_values = self._get_tagged_values(class_elem)
        
        # Create properties and track required fields
        properties = {}
        required = []
        
        # Process attributes
        attributes = class_elem.get('ownedAttribute', [])
        if not isinstance(attributes, list):
            attributes = [attributes]
            
        for attribute in attributes:
            if attribute.get('@xmi:type') == 'uml:Property':
                attr_name = attribute.get('@name', '')
                if attr_name:
                    prop_def = self._create_property_definition(attribute)
                    
                    # Add attribute tagged values
                    attr_tagged_values = self._get_tagged_values(attribute)
                    if attr_tagged_values:
                        prop_def['x-uml-tagged-value'] = attr_tagged_values
                    
                    properties[attr_name] = prop_def
                    
                    # Check if property is required
                    is_required = attribute.get('@isRequired', 'false').lower() == 'true'
                    lower = attribute.get('@lower', '0')
                    if is_required or lower != '0':
                        required.append(attr_name)
        
        # Create the schema
        schema = {
            '$schema': 'http://json-schema.org/draft-07/schema#',
            'type': 'object',
            'title': name,
            'description': tagged_values.get('documentation', f'Represents a {name} in the system'),
            'properties': properties
        }
        
        # Add required fields if any
        if required:
            schema['required'] = required
        
        # Add class-level tagged values
        if tagged_values:
            schema['x-uml-tagged-value'] = tagged_values
        
        return schema

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
                    name = class_elem.get('@name', '')
                    if name:
                        # Generate schema
                        schema = self._convert_class_to_schema(class_elem)
                        
                        # Sanitize filename
                        safe_name = self._sanitize_filename(name)
                        
                        # Save schema to file
                        schema_file = self.schema_folder / f"{safe_name}.json"
                        with open(schema_file, 'w', encoding='utf-8') as f:
                            json.dump(schema, f, indent=2, ensure_ascii=False)
                            
                        self.schemas[name] = schema
                        logging.info(f"Generated schema for class: {name}")
                except Exception as e:
                    logging.error(f"Error processing class {name}: {str(e)}")
                    
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
    # Get version folder from command line argument or use default
    version_folder = sys.argv[1] if len(sys.argv) > 1 else "v2.1.0"
    
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
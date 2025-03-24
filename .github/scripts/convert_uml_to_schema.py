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
import xml.etree.ElementTree as ET
import re
import io

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
        self.namespaces = {'xmi': 'http://schema.omg.org/UML', 'uml': 'http://schema.omg.org/UML'}

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

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize a filename by removing invalid characters and replacing spaces with underscores.
        
        Args:
            filename: The filename to sanitize
            
        Returns:
            The sanitized filename
        """
        # First normalize any newlines to spaces
        filename = filename.replace('\n', ' ').replace('\r', ' ')
        
        # Remove any backslashes or forward slashes
        filename = filename.replace('\\', '_').replace('/', '_')
        
        # Replace any other non-alphanumeric characters with underscores
        filename = re.sub(r'[^a-zA-Z0-9]', '_', filename)
        
        # Remove multiple consecutive underscores
        filename = re.sub(r'_+', '_', filename)
        
        # Remove leading/trailing underscores and whitespace
        filename = filename.strip('_ ')
        
        # Convert to lowercase
        filename = filename.lower()
        
        # Limit filename length to 100 characters
        if len(filename) > 100:
            filename = filename[:100]
        
        # Ensure the filename is not empty
        if not filename:
            filename = 'unnamed'
        
        return filename

    def process_xmi_file(self, file_path: Path) -> None:
        """Process an XMI file and generate JSON Schema files.
        
        Args:
            file_path: Path to the XMI file
        """
        try:
            # Read and parse the file
            content = self.read_file_with_encoding(file_path)
            if not content:
                return
            
            # Try to parse XML with error handling
            try:
                # First try with ElementTree
                tree = ET.parse(io.StringIO(content))
                root = tree.getroot()
            except ET.ParseError as e:
                # If ElementTree fails, try with xmltodict
                try:
                    xmi_data = xmltodict.parse(content)
                    if 'xmi:XMI' in xmi_data:
                        model = xmi_data['xmi:XMI'].get('uml:Model', {})
                        if model and 'packagedElement' in model:
                            self._process_package_elements(model['packagedElement'])
                        return
                except Exception as e:
                    logging.error(f"Failed to parse XML file {file_path}: {str(e)}")
                    return
            
            # Process each UML class
            for class_elem in root.findall('.//packagedElement[@xmi:type="uml:Class"]', self.namespaces):
                name = class_elem.get('name', '')
                if name:
                    # Generate schema
                    schema = self._convert_class_to_schema(class_elem)
                    
                    # Save schema to file
                    schema_file = self.schema_folder / f"{self._sanitize_filename(name)}.json"
                    with open(schema_file, 'w', encoding='utf-8') as f:
                        json.dump(schema, f, indent=2, ensure_ascii=False)
            
            # Process each UML component
            for component in root.findall('.//packagedElement[@xmi:type="uml:Component"]', self.namespaces):
                name = component.get('name', '')
                if name:
                    # Generate schema
                    schema = self._convert_class_to_schema(component)
                    
                    # Save schema to file
                    schema_file = self.schema_folder / f"{self._sanitize_filename(name)}.json"
                    with open(schema_file, 'w', encoding='utf-8') as f:
                        json.dump(schema, f, indent=2, ensure_ascii=False)
            
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

    def _get_class_description(self, class_elem: Union[ET.Element, dict]) -> str:
        """Get a meaningful description for a UML class.
        
        Args:
            class_elem: The UML class element or dictionary
            
        Returns:
            A meaningful description of the class
        """
        if isinstance(class_elem, dict):
            name = class_elem.get('@name', '')
            doc = class_elem.get('@documentation', '')
            if doc:
                return doc.strip()
            return f"Represents a {name} in the system"
        
        # ElementTree element
        doc = class_elem.find('.//ownedComment[@xmi:type="uml:Comment"]', self.namespaces)
        if doc is not None:
            return doc.get('body', '').strip()
        
        name = class_elem.get('name', '')
        return f"Represents a {name} in the system"

    def _create_property_definition(self, attr: Union[ET.Element, dict], class_elem: Union[ET.Element, dict]) -> Dict[str, Any]:
        """Create a JSON Schema property definition from a UML attribute.
        
        Args:
            attr: The UML attribute element or dictionary
            class_elem: The parent UML class element or dictionary
            
        Returns:
            A JSON Schema property definition
        """
        if isinstance(attr, dict):
            name = attr.get('@name', '')
            doc = attr.get('@documentation', '')
            type_info = attr.get('type', {})
            type_name = type_info.get('@name', '')
            lower = attr.get('@lowerBound', '0')
            upper = attr.get('@upperBound', '1')
        else:
            name = attr.get('name', '')
            doc = attr.find('.//ownedComment[@xmi:type="uml:Comment"]', self.namespaces)
            doc = doc.get('body', '').strip() if doc is not None else ''
            type_elem = attr.find('.//type', self.namespaces)
            type_name = type_elem.get('name', '') if type_elem is not None else ''
            lower = attr.get('lowerValue', '0')
            upper = attr.get('upperValue', '1')
        
        description = doc if doc else f"Property {name}"
        
        # Create property definition
        prop_def = {
            'description': description,
            'type': 'string'  # Default type
        }
        
        # Add format based on type name
        if type_name:
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
        if upper == '*' or (upper.isdigit() and int(upper) > 1):
            return {
                'type': 'array',
                'items': prop_def,
                'minItems': int(lower) if lower.isdigit() else 0
            }
        
        return prop_def

    def _get_tagged_values(self, element: Union[ET.Element, dict]) -> Dict[str, str]:
        """Extract tagged values from a UML element.
        
        Args:
            element: The UML element or dictionary
            
        Returns:
            Dictionary of tagged values
        """
        tagged_values = {}
        
        if isinstance(element, dict):
            # Handle dictionary format
            if 'taggedValue' in element:
                tagged_values_elem = element['taggedValue']
                if not isinstance(tagged_values_elem, list):
                    tagged_values_elem = [tagged_values_elem]
                
                for tv in tagged_values_elem:
                    if isinstance(tv, dict):
                        key = tv.get('@key', '')
                        value = tv.get('@value', '')
                        if key and value:
                            tagged_values[key] = value
        else:
            # Handle ElementTree format
            for tv in element.findall('.//taggedValue', self.namespaces):
                key = tv.get('key', '')
                value = tv.get('value', '')
                if key and value:
                    tagged_values[key] = value
        
        return tagged_values

    def _convert_class_to_schema(self, class_elem: Union[ET.Element, dict]) -> Dict[str, Any]:
        """Convert a UML class to a JSON Schema.
        
        Args:
            class_elem: The UML class element or dictionary
            
        Returns:
            A JSON Schema representation of the class
        """
        if isinstance(class_elem, dict):
            name = class_elem.get('@name', '')
            description = self._get_class_description(class_elem)
            attributes = class_elem.get('ownedAttribute', [])
            if not isinstance(attributes, list):
                attributes = [attributes]
        else:
            name = class_elem.get('name', '')
            description = self._get_class_description(class_elem)
            attributes = class_elem.findall('.//ownedAttribute', self.namespaces)
        
        # Create properties and track required fields
        properties = {}
        required = []
        
        for attr in attributes:
            if isinstance(attr, dict):
                attr_name = attr.get('@name', '')
                # Skip association ends
                if 'association' in attr:
                    continue
            else:
                attr_name = attr.get('name', '')
                # Skip association ends
                if attr.find('.//association', self.namespaces) is not None:
                    continue
            
            if attr_name:
                prop_def = self._create_property_definition(attr, class_elem)
                
                # Add tagged values for the attribute
                attr_tagged_values = self._get_tagged_values(attr)
                if attr_tagged_values:
                    prop_def['x-uml-tagged-value'] = attr_tagged_values
                
                properties[attr_name] = prop_def
                
                # Check if property is required
                if isinstance(attr, dict):
                    lower = attr.get('@lowerBound', '0')
                else:
                    lower = attr.get('lowerValue', '0')
                
                if lower != '0':
                    required.append(attr_name)
        
        # Create the schema
        schema = {
            '$schema': 'http://json-schema.org/draft-07/schema#',
            'type': 'object',
            'title': name,
            'description': description,
            'properties': properties
        }
        
        # Add required fields if any
        if required:
            schema['required'] = required
        
        # Add class-level tagged values
        class_tagged_values = self._get_tagged_values(class_elem)
        if class_tagged_values:
            schema['x-uml-tagged-value'] = class_tagged_values
        
        return schema

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
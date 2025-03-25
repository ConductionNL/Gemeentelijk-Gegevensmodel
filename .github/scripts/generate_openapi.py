#!/usr/bin/env python3

"""
OpenAPI Specification Generator
This script generates an OpenAPI specification from existing JSON Schema files.
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Any
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(levelname)s - %(message)s')

class OpenAPIGenerator:
    """
    Generates OpenAPI specification from JSON Schema files.
    """
    
    def __init__(self, version_folder: str):
        """
        Initialize the OpenAPI generator.

        Args:
            version_folder (str): Path to the version folder containing schema files
        """
        self.version_folder = Path(version_folder)
        self.schema_folder = self.version_folder / 'schemas'
        self.schemas: Dict[str, dict] = {}

    def load_schemas(self) -> None:
        """Load all JSON schema files from the schema folder."""
        if not self.schema_folder.exists():
            logging.error(f"Schema folder not found: {self.schema_folder}")
            return

        # Load all JSON files except openapi.json
        for schema_file in self.schema_folder.glob("*.json"):
            if schema_file.name != "openapi.json":
                try:
                    with open(schema_file, 'r', encoding='utf-8') as f:
                        schema = json.load(f)
                        # Use the title as the schema name, or filename if no title
                        schema_name = schema.get('title', schema_file.stem)
                        self.schemas[schema_name] = schema
                        logging.info(f"Loaded schema: {schema_name}")
                except Exception as e:
                    logging.error(f"Error loading schema {schema_file}: {str(e)}")

    def generate_openapi_spec(self) -> dict:
        """
        Generate OpenAPI specification from the loaded schemas.

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

    def save_openapi_spec(self, spec: dict) -> None:
        """
        Save the OpenAPI specification to a file.

        Args:
            spec (dict): The OpenAPI specification to save
        """
        openapi_file = self.schema_folder / "openapi.json"
        try:
            with open(openapi_file, 'w', encoding='utf-8') as f:
                json.dump(spec, f, indent=2, ensure_ascii=False)
            logging.info(f"Saved OpenAPI spec to {openapi_file}")
        except Exception as e:
            logging.error(f"Error saving OpenAPI spec: {str(e)}")

def main():
    """
    Main entry point for the OpenAPI spec generator.
    """
    # Get version folder from command line argument
    if len(sys.argv) > 1:
        version_folder = sys.argv[1]
    else:
        logging.error("No version folder specified")
        sys.exit(1)
    
    try:
        generator = OpenAPIGenerator(version_folder)
        generator.load_schemas()
        
        if not generator.schemas:
            logging.error("No schemas found to generate OpenAPI spec")
            sys.exit(1)
            
        spec = generator.generate_openapi_spec()
        generator.save_openapi_spec(spec)
        logging.info("OpenAPI spec generation completed successfully")
        
    except Exception as e:
        logging.error(f"OpenAPI spec generation failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 
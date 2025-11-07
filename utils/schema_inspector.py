"""
Database schema discovery and inspection
"""
from sqlalchemy import inspect
from .db_manager import get_db_chain


def get_database_schema_info(db_config: dict) -> dict:
    """
    Automatically extracts complete database schema information
    NO hardcoding - works with ANY database structure
    """
    db = get_db_chain(db_config)
    engine = db._engine
    inspector = inspect(engine)
    
    schema_info = {
        'tables': {},
        'relationships': [],
        'description': ""
    }
    
    # Extract all table information
    for table_name in inspector.get_table_names():
        columns = inspector.get_columns(table_name)
        pk = inspector.get_pk_constraint(table_name)
        fks = inspector.get_foreign_keys(table_name)
        
        # Get sample data to understand content
        try:
            sample_query = f"SELECT * FROM {table_name} LIMIT 3"
            sample_data = db.run(sample_query)
        except:
            sample_data = "No sample data available"
        
        schema_info['tables'][table_name] = {
            'columns': [
                {
                    'name': col['name'],
                    'type': str(col['type']),
                    'nullable': col['nullable']
                } for col in columns
            ],
            'primary_key': pk.get('constrained_columns', []),
            'foreign_keys': fks,
            'sample_data': sample_data
        }
        
        # Track relationships
        for fk in fks:
            schema_info['relationships'].append({
                'from_table': table_name,
                'from_column': fk['constrained_columns'][0] if fk['constrained_columns'] else None,
                'to_table': fk['referred_table'],
                'to_column': fk['referred_columns'][0] if fk['referred_columns'] else None
            })
    
    # Generate human-readable description
    description = "DATABASE SCHEMA:\n\n"
    for table_name, info in schema_info['tables'].items():
        description += f"📊 Table: {table_name}\n"
        description += f"   Columns: {', '.join([col['name'] + ' (' + col['type'] + ')' for col in info['columns']])}\n"
        if info['foreign_keys']:
            for fk in info['foreign_keys']:
                description += f"   🔗 Links to: {fk['referred_table']}\n"
        description += f"   Sample: {str(info['sample_data'])[:100]}...\n\n"
    
    schema_info['description'] = description
    return schema_info

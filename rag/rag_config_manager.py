#!/usr/bin/env python3
"""
RAG Configuration Manager
Professional tool for managing RAG configuration settings
"""

import argparse
import json
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from rag.config.rag_config import RAGConfigManager, RAGConfig

def show_current_config():
    """Show current configuration with explanations"""
    print("🔧 Current RAG Configuration")
    print("=" * 50)
    print("📖 For detailed explanations, see: rag/config/CONFIG_EXPLANATION.md")
    print()
    
    config_manager = RAGConfigManager()
    config = config_manager.config
    
    print(f"Environment: {config.environment}")
    print(f"Debug Mode: {config.debug_mode}")
    print(f"Log Level: {config.log_level}")
    print()
    
    print("📊 Search Settings:")
    print(f"  Default Score Threshold: {config.search.default_score_threshold} (0.01=more results, 0.1=fewer but better)")
    print(f"  Min Score Threshold: {config.search.min_score_threshold} (minimum allowed)")
    print(f"  Max Score Threshold: {config.search.max_score_threshold} (maximum allowed)")
    print(f"  Default Max Results: {config.search.default_max_results} (max search results)")
    print(f"  Default Max Docs: {config.search.default_max_docs} (max docs for context)")
    print(f"  Max Context Length: {config.search.default_max_context_length} (max chars in prompt)")
    print()
    
    print("📄 Document Settings:")
    print(f"  Default Chunk Size: {config.document.default_chunk_size} (200=small, 2000=large)")
    print(f"  Default Chunk Overlap: {config.document.default_chunk_overlap} (overlap between chunks)")
    print(f"  Max File Size: {config.document.max_file_size_mb} MB (max file size to process)")
    print(f"  Supported Extensions: {config.document.supported_extensions} (file types supported)")
    print()
    
    print("🗄️ Database Settings:")
    print(f"  DB Path: {config.database.default_db_path} (where ChromaDB stores data)")
    print(f"  Collection Name: {config.database.default_collection_name} (document collection name)")
    print(f"  Embedding Model: {config.database.default_embedding_model} (AI model for text vectors)")
    print()
    
    print("🌐 API Settings:")
    print(f"  Rate Limit: {config.api.default_rate_limit} requests/hour (max API calls per user)")
    print(f"  Max Prompt Length: {config.api.max_prompt_length} (max chars in user prompts)")
    print(f"  Default Timeout: {config.api.default_timeout}s (request timeout)")

def update_threshold(new_threshold):
    """Update search threshold"""
    print(f"🔧 Updating search threshold to {new_threshold}")
    
    config_manager = RAGConfigManager()
    
    # Validate threshold
    if not config_manager.validate_threshold(new_threshold):
        print(f"❌ Invalid threshold: {new_threshold}")
        print(f"   Must be between {config_manager.config.search.min_score_threshold} and {config_manager.config.search.max_score_threshold}")
        return False
    
    # Update threshold
    config_manager.config.search.default_score_threshold = new_threshold
    
    # Save configuration
    if config_manager.save_config():
        print(f"✅ Threshold updated to {new_threshold}")
        return True
    else:
        print("❌ Failed to save configuration")
        return False

def update_setting(category, setting, value):
    """Update a specific setting"""
    print(f"🔧 Updating {category}.{setting} to {value}")
    
    config_manager = RAGConfigManager()
    config = config_manager.config
    
    try:
        # Update the setting
        if category == 'search':
            setattr(config.search, setting, value)
        elif category == 'document':
            setattr(config.document, setting, value)
        elif category == 'database':
            setattr(config.database, setting, value)
        elif category == 'api':
            setattr(config.api, setting, value)
        else:
            print(f"❌ Unknown category: {category}")
            return False
        
        # Save configuration
        if config_manager.save_config():
            print(f"✅ {category}.{setting} updated to {value}")
            return True
        else:
            print("❌ Failed to save configuration")
            return False
            
    except Exception as e:
        print(f"❌ Error updating setting: {e}")
        return False

def reset_to_defaults():
    """Reset configuration to defaults"""
    print("🔄 Resetting configuration to defaults")
    
    config_manager = RAGConfigManager()
    
    # Create default configuration
    default_config = RAGConfig()
    config_manager.config = default_config
    
    # Save configuration
    if config_manager.save_config():
        print("✅ Configuration reset to defaults")
        return True
    else:
        print("❌ Failed to save configuration")
        return False

def export_config(output_file):
    """Export configuration to file"""
    print(f"📤 Exporting configuration to {output_file}")
    
    config_manager = RAGConfigManager()
    
    if config_manager.save_config(output_file):
        print(f"✅ Configuration exported to {output_file}")
        return True
    else:
        print("❌ Failed to export configuration")
        return False

def import_config(input_file):
    """Import configuration from file"""
    print(f"📥 Importing configuration from {input_file}")
    
    if not os.path.exists(input_file):
        print(f"❌ Configuration file not found: {input_file}")
        return False
    
    try:
        # Load configuration from file
        with open(input_file, 'r') as f:
            config_data = json.load(f)
        
        # Create new configuration manager with the file
        config_manager = RAGConfigManager(input_file)
        
        # Save to default location
        if config_manager.save_config():
            print(f"✅ Configuration imported from {input_file}")
            return True
        else:
            print("❌ Failed to save imported configuration")
            return False
            
    except Exception as e:
        print(f"❌ Error importing configuration: {e}")
        return False

def show_threshold_help():
    """Show threshold explanations"""
    print("🎯 RAG Threshold Explanations")
    print("=" * 50)
    print()
    print("📊 SEARCH THRESHOLDS:")
    print("  default_score_threshold: Main search threshold")
    print("    • 0.01 = More results, lower quality (high recall)")
    print("    • 0.05 = Balanced results (recommended)")
    print("    • 0.1  = Fewer results, higher quality (high precision)")
    print("    • 0.2  = Very strict, only highly relevant documents")
    print()
    print("📄 DOCUMENT THRESHOLDS:")
    print("  default_chunk_size: Size of text chunks")
    print("    • 500  = Small chunks, more precise but less context")
    print("    • 1000 = Balanced chunks (recommended)")
    print("    • 1500 = Large chunks, more context but less precise")
    print("    • 2000 = Very large chunks, maximum context")
    print()
    print("🌐 API THRESHOLDS:")
    print("  default_rate_limit: API requests per hour")
    print("    • 50   = Conservative limit")
    print("    • 100  = Standard limit (recommended)")
    print("    • 200  = High limit for active users")
    print("    • 500  = Very high limit for enterprise")
    print()
    print("📖 For complete documentation, see: rag/config/CONFIG_EXPLANATION.md")
    print()

def main():
    parser = argparse.ArgumentParser(description="RAG Configuration Manager")
    parser.add_argument("--show", action="store_true", help="Show current configuration")
    parser.add_argument("--threshold", type=float, help="Update search threshold")
    parser.add_argument("--setting", nargs=3, metavar=('CATEGORY', 'SETTING', 'VALUE'), 
                       help="Update a specific setting (category setting value)")
    parser.add_argument("--reset", action="store_true", help="Reset to default configuration")
    parser.add_argument("--export", type=str, help="Export configuration to file")
    parser.add_argument("--import", type=str, dest="import_file", help="Import configuration from file")
    parser.add_argument("--help-thresholds", action="store_true", help="Show threshold explanations")
    
    args = parser.parse_args()
    
    if args.help_thresholds:
        show_threshold_help()
    elif args.show:
        show_current_config()
    elif args.threshold is not None:
        update_threshold(args.threshold)
    elif args.setting:
        category, setting, value = args.setting
        # Try to convert value to appropriate type
        try:
            if value.lower() in ['true', 'false']:
                value = value.lower() == 'true'
            elif value.isdigit():
                value = int(value)
            elif '.' in value and value.replace('.', '').isdigit():
                value = float(value)
        except:
            pass  # Keep as string
        update_setting(category, setting, value)
    elif args.reset:
        reset_to_defaults()
    elif args.export:
        export_config(args.export)
    elif args.import_file:
        import_config(args.import_file)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

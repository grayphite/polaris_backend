#!/usr/bin/env python3
"""
Simple RAG Data Deletion Script

This script completely deletes all RAG data and "undoes" the training.

Usage:
    python rag/delete_all_data.py
"""

import os
import sys
import shutil
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from rag.rag_manager import JuridicalRAGManager

def delete_all_rag_data():
    """Delete all RAG data - one simple method that works"""
    print("🗑️ DELETING ALL RAG DATA")
    print("=" * 40)
    
    try:
        # Initialize RAG manager
        rag_manager = JuridicalRAGManager()
        db_path = Path(rag_manager.chroma_db_path)
        
        print(f"Database path: {db_path}")
        
        # Check current state
        try:
            count_before = rag_manager.collection.count()
            print(f"Documents before deletion: {count_before}")
        except:
            count_before = 0
            print("Collection not accessible")
        
        if count_before > 0:
            # Method 1: Clear the collection (production-safe)
            print("Clearing collection data...")
            rag_manager.clear_collection()
            print("✅ Collection cleared!")
            
            # Verify collection is empty
            count_after_clear = rag_manager.collection.count()
            print(f"Documents after clear: {count_after_clear}")
            
            if count_after_clear == 0:
                print("✅ Collection successfully cleared!")
            else:
                # Method 2: Delete and recreate collection (if clear didn't work)
                print("Collection not fully cleared, deleting and recreating...")
                try:
                    collection_name = rag_manager.collection_name
                    client = rag_manager.client
                    
                    # Delete the collection
                    client.delete_collection(collection_name)
                    print("✅ Collection deleted!")
                    
                    # Recreate empty collection
                    rag_manager._init_chromadb()
                    print("✅ Empty collection recreated!")
                    
                except Exception as e:
                    print(f"⚠️ Error with collection deletion: {e}")
        else:
            print("✅ Collection is already empty")
        
        # Final verification
        print("Verifying deletion...")
        rag_manager_new = JuridicalRAGManager()
        count_after = rag_manager_new.collection.count()
        print(f"Documents after deletion: {count_after}")
        
        if count_after == 0:
            print("✅ SUCCESS: All RAG data deleted!")
            print("✅ RAG system is now completely clean")
            print("✅ Ready for fresh document upload")
            return True
        else:
            print("⚠️ Warning: Some data might still exist")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    print("🗑️ RAG DATA DELETION")
    print("=" * 30)
    print("This will delete all RAG data while preserving the database structure.")
    print("Production-safe: Only clears data, keeps database intact.")
    print()
    
    # For non-interactive use, add --force flag
    import sys
    force_mode = '--force' in sys.argv
    
    if force_mode:
        print("🚀 Force mode: Proceeding without confirmation")
        success = delete_all_rag_data()
    else:
        # Ask for confirmation
        try:
            response = input("Are you sure? (yes/no): ").lower().strip()
        except EOFError:
            print("❌ Interactive input not available. Use --force flag for non-interactive mode")
            return
        
        if response in ['yes', 'y']:
            success = delete_all_rag_data()
        else:
            print("❌ Deletion cancelled")
            return
    
    if success:
        print()
        print("🎉 RAG DATA DELETION COMPLETE!")
        print("=" * 40)
        print("✅ All documents removed")
        print("✅ All embeddings deleted") 
        print("✅ All search indexes cleared")
        print("✅ System reset to initial state")
        print()
        print("You can now add fresh documents to RAG")
    else:
        print()
        print("❌ Deletion may not have completed successfully")

if __name__ == "__main__":
    main()

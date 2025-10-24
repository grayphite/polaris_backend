#!/usr/bin/env python3
"""
Simple RAG File Addition Script

Usage:
    python rag/add_files.py --file path/to/file.pdf
    python rag/add_files.py --folder path/to/folder/
    python rag/add_files.py --url https://example.com/document.pdf
    python rag/add_files.py --list
    python rag/add_files.py --search "query"
"""

import os
import sys
import argparse
import requests
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from rag.rag_manager import JuridicalRAGManager
from rag.document_processor import DocumentProcessor

def add_single_file(file_path):
    """Add a single file to RAG"""
    print(f"📄 Adding file: {file_path}")
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False
    
    try:
        rag_manager = JuridicalRAGManager()
        processor = DocumentProcessor()
        
        result = processor.process_document(file_path)
        if not result or not result.get('success', False):
            print(f"❌ No content extracted from {file_path}")
            return False
        
        chunks = result.get('chunks', [])
        if not chunks:
            print(f"❌ No chunks created from {file_path}")
            return False
        
        rag_manager.add_chunks(chunks)
        print(f"✅ Added {len(chunks)} chunks from {os.path.basename(file_path)}")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def add_folder(folder_path):
    """Add all supported files from a folder"""
    print(f"📁 Adding files from folder: {folder_path}")
    
    if not os.path.exists(folder_path):
        print(f"❌ Folder not found: {folder_path}")
        return False
    
    try:
        rag_manager = JuridicalRAGManager()
        processor = DocumentProcessor()
        
        supported_extensions = [".pdf", ".docx", ".doc", ".txt"]
        folder = Path(folder_path)
        files = []
        
        for ext in supported_extensions:
            files.extend(folder.rglob(f"*{ext}"))
            files.extend(folder.rglob(f"*{ext.upper()}"))
        
        if not files:
            print(f"❌ No supported files found. Supported: {supported_extensions}")
            return False
        
        print(f"📋 Found {len(files)} files")
        total_chunks = 0
        successful = 0
        
        for file_path in files:
            try:
                print(f"🔄 Processing: {file_path.name}")
                result = processor.process_document(str(file_path))
                
                if result and result.get('success', False):
                    chunks = result.get('chunks', [])
                    if chunks:
                        rag_manager.add_chunks(chunks)
                        total_chunks += len(chunks)
                        successful += 1
                        print(f"✅ Added {len(chunks)} chunks")
                    else:
                        print(f"⚠️ No chunks created")
                else:
                    print(f"⚠️ No content extracted")
                    
            except Exception as e:
                print(f"❌ Error processing {file_path.name}: {e}")
        
        print(f"🎉 Successfully processed {successful}/{len(files)} files")
        print(f"📊 Total chunks added: {total_chunks}")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def add_from_url(url, filename=None):
    """Add document from URL"""
    print(f"🌐 Adding from URL: {url}")
    
    try:
        rag_manager = JuridicalRAGManager()
        processor = DocumentProcessor()
        
        # Download
        print("⬇️ Downloading...")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        # Save temp file
        if not filename:
            filename = url.split('/')[-1] or f"downloaded_{hash(url) % 10000}.pdf"
        
        temp_path = f"./temp_{filename}"
        with open(temp_path, "wb") as f:
            f.write(response.content)
        
        # Process
        print("🔄 Processing...")
        result = processor.process_document(temp_path)
        
        if not result or not result.get('success', False):
            print("❌ No content extracted")
            os.remove(temp_path)
            return False
        
        chunks = result.get('chunks', [])
        if not chunks:
            print("❌ No chunks created")
            os.remove(temp_path)
            return False
        
        rag_manager.add_chunks(chunks)
        os.remove(temp_path)
        
        print(f"✅ Added {len(chunks)} chunks from URL")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        return False

def list_documents():
    """List all documents in RAG"""
    print("📋 Documents in RAG System:")
    print("=" * 40)
    
    try:
        rag_manager = JuridicalRAGManager()
        collection = rag_manager.collection
        count = collection.count()
        
        print(f"Total documents: {count}")
        
        if count == 0:
            print("No documents found.")
            return
        
        # Get unique sources
        results = collection.get()
        sources = set()
        for metadata in results["metadatas"]:
            if metadata:
                # Check both 'source' and 'source_file' fields
                source_field = metadata.get("source") or metadata.get("source_file")
                if source_field:
                    sources.add(source_field)
        
        print(f"Unique documents: {len(sources)}")
        for i, source in enumerate(sorted(sources), 1):
            print(f"{i:2d}. {source}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def search_documents(query, k=5):
    """Search documents"""
    print(f"🔍 Searching: '{query}'")
    print("=" * 40)
    
    try:
        rag_manager = JuridicalRAGManager()
        results = rag_manager.search_relevant_docs(query, k=k, score_threshold=0.01)
        
        if not results:
            print("No relevant documents found.")
            return
        
        print(f"Found {len(results)} relevant documents:")
        for i, result in enumerate(results, 1):
            source = result.get("source", "Unknown")
            score = result.get("score", 0)
            content = result.get("text", "")
            
            print(f"\n{i}. {source} (score: {score:.4f})")
            print(f"   {content[:150]}...")
            
    except Exception as e:
        print(f"❌ Error: {e}")

def delete_document(filename):
    """Delete a specific document from RAG"""
    print(f"🗑️ Deleting document: {filename}")
    print("=" * 40)
    
    try:
        rag_manager = JuridicalRAGManager()
        collection = rag_manager.collection
        
        # Get all documents to find matching ones
        results = collection.get()
        
        # Find documents with matching source
        ids_to_delete = []
        for i, metadata in enumerate(results["metadatas"]):
            if metadata:
                # Check both 'source' and 'source_file' fields
                source_field = metadata.get("source") or metadata.get("source_file")
                if source_field:
                    if source_field == filename or filename in source_field:
                        ids_to_delete.append(results["ids"][i])
        
        if not ids_to_delete:
            print(f"❌ No documents found with name: {filename}")
            return False
        
        # Delete the documents
        collection.delete(ids=ids_to_delete)
        
        print(f"✅ Deleted {len(ids_to_delete)} chunks from {filename}")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def clear_all_documents():
    """Clear all documents from RAG"""
    print("🗑️ Clearing ALL documents from RAG")
    print("=" * 40)
    
    try:
        rag_manager = JuridicalRAGManager()
        collection = rag_manager.collection
        
        # Get count before deletion
        count_before = collection.count()
        
        if count_before == 0:
            print("❌ No documents to delete")
            return False
        
        # Clear all documents
        rag_manager.clear_collection()
        
        print(f"✅ Deleted all {count_before} documents from RAG")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="RAG File Manager")
    parser.add_argument("--file", help="Add a single file")
    parser.add_argument("--folder", help="Add all files from folder")
    parser.add_argument("--url", help="Add document from URL")
    parser.add_argument("--list", action="store_true", help="List all documents")
    parser.add_argument("--search", help="Search documents")
    parser.add_argument("--delete", help="Delete a specific document by filename")
    parser.add_argument("--clear", action="store_true", help="Clear all documents")
    parser.add_argument("--k", type=int, default=5, help="Number of search results (default: 5)")
    
    args = parser.parse_args()
    
    if args.file:
        add_single_file(args.file)
    elif args.folder:
        add_folder(args.folder)
    elif args.url:
        add_from_url(args.url)
    elif args.list:
        list_documents()
    elif args.search:
        search_documents(args.search, args.k)
    elif args.delete:
        delete_document(args.delete)
    elif args.clear:
        clear_all_documents()
    else:
        print("🚀 RAG File Manager")
        print("=" * 30)
        print("Usage:")
        print("  python rag/add_files.py --file path/to/file.pdf")
        print("  python rag/add_files.py --folder path/to/folder/")
        print("  python rag/add_files.py --url https://example.com/doc.pdf")
        print("  python rag/add_files.py --list")
        print("  python rag/add_files.py --search \"query\"")
        print("  python rag/add_files.py --delete filename.txt")
        print("  python rag/add_files.py --clear")

if __name__ == "__main__":
    main()

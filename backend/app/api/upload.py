"""File upload endpoint for RAG knowledge base."""

import io
import os
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from pydantic import BaseModel
from langchain_openai import OpenAIEmbeddings

from app.core.supabase_client import get_supabase
from app.core.database import resolve_tenant_uuid

logger = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])


class UploadResponse(BaseModel):
    success: bool
    message: str
    chunks_created: int = 0


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF using PyMuPDF."""
    import fitz  # PyMuPDF
    
    text_parts = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            text_parts.append(page.get_text())
    
    return "\n".join(text_parts)


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text from DOCX using python-docx."""
    from docx import Document
    
    doc = Document(io.BytesIO(file_bytes))
    text_parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)
    
    return "\n".join(text_parts)


def extract_text_from_txt(file_bytes: bytes) -> str:
    """Extract text from plain text file."""
    return file_bytes.decode("utf-8", errors="ignore")


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks."""
    if not text:
        return []
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
    
    return chunks


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    tenant_id: str = Form(default="73ee1a5c-1160-4a51-ba34-3fdddcd49f9e"),
    category: str = Form(default="manual"),
):
    """
    Upload a file (PDF, DOCX, TXT) to the knowledge base.
    
    The file is processed, chunked, embedded, and stored in Supabase.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    # Validate file type
    ext = file.filename.lower().split(".")[-1]
    if ext not in ["pdf", "docx", "doc", "txt"]:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use PDF, DOCX, or TXT.")
    
    # Read file content
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")
    
    # Extract text based on file type
    try:
        if ext == "pdf":
            text = extract_text_from_pdf(file_bytes)
        elif ext in ["docx", "doc"]:
            text = extract_text_from_docx(file_bytes)
        else:  # txt
            text = extract_text_from_txt(file_bytes)
    except Exception as e:
        logger.error(f"Failed to extract text from {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to extract text: {str(e)}")
    
    if not text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from the file")
    
    if os.getenv("DEBUG"):
        logger.info(f"Extracted {len(text)} characters from {file.filename}")
    
    # Chunk text
    chunks = chunk_text(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="No valid chunks could be created")
    
    if os.getenv("DEBUG"):
        logger.info(f"Created {len(chunks)} chunks")
    
    # Generate embeddings
    try:
        embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
        embeddings = embeddings_model.embed_documents(chunks)
    except Exception as e:
        logger.error(f"Failed to generate embeddings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate embeddings: {str(e)}")
    
    # Resolve tenant UUID
    tenant_uuid = resolve_tenant_uuid(tenant_id)
    
    # Store in Supabase
    supabase = get_supabase()
    chunks_created = 0
    
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        try:
            supabase.table("knowledge_base").insert({
                "tenant_id": tenant_uuid,
                "category": category,
                "metadata": {
                    "title": f"{file.filename} - Parte {i+1}",
                    "content": chunk,
                    "source": file.filename,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "file_size": len(file_bytes) # Store exact file size
                },
                "embedding": embedding,
                "is_active": True
            }).execute()
            chunks_created += 1
        except Exception as e:
            logger.error(f"Failed to insert chunk {i}: {e}")
            # Continue with other chunks
    
    if chunks_created == 0:
        raise HTTPException(status_code=500, detail="Failed to store any chunks in the database")
    
    return UploadResponse(
        success=True,
        message=f"Successfully processed {file.filename}",
        chunks_created=chunks_created
    )


class DeleteRequest(BaseModel):
    filename: str
    tenant_id: str = "00000000-0000-0000-0000-000000000001"


class DeleteResponse(BaseModel):
    success: bool
    message: str
    deleted_count: int = 0


@router.post("/delete-knowledge", response_model=DeleteResponse)
async def delete_knowledge(request: DeleteRequest):
    """
    Delete all knowledge_base entries for a specific source file.
    
    Uses metadata->>'source' to match the filename.
    """
    if not request.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    tenant_uuid = resolve_tenant_uuid(request.tenant_id)
    logger.info(f"DELETE: tenant_id input='{request.tenant_id}', resolved='{tenant_uuid}'")
    logger.info(f"DELETE: filename='{request.filename}'")
    
    supabase = get_supabase()
    
    try:
        # Fetch all entries for this tenant with metadata
        result = supabase.table("knowledge_base").select("id, metadata").eq("tenant_id", tenant_uuid).execute()
        logger.info(f"DELETE: Query returned {len(result.data)} entries for tenant")
        
        # Filter by source in metadata
        ids_to_delete = []
        for item in result.data:
            metadata = item.get("metadata", {})
            source = metadata.get("source", "") if isinstance(metadata, dict) else ""
            if source == request.filename:
                ids_to_delete.append(item["id"])
        
        logger.info(f"DELETE: Found {len(ids_to_delete)} entries matching filename")
        
        # Delete each matching entry
        deleted_count = 0
        for id_to_delete in ids_to_delete:
            try:
                supabase.table("knowledge_base").delete().eq("id", id_to_delete).execute()
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete entry {id_to_delete}: {e}")
        
        if deleted_count == 0:
            return DeleteResponse(
                success=False,
                message=f"No entries found for file: {request.filename}",
                deleted_count=0
            )
        
        return DeleteResponse(
            success=True,
            message=f"Deleted {deleted_count} chunks for {request.filename}",
            deleted_count=deleted_count
        )
        
    except Exception as e:
        logger.error(f"Failed to delete knowledge entries: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete: {str(e)}")


class KnowledgeFile(BaseModel):
    filename: str
    chunks: int
    category: str


class ListKnowledgeResponse(BaseModel):
    success: bool
    files: list[KnowledgeFile]


@router.get("/list-knowledge")
async def list_knowledge(tenant_id: str = "00000000-0000-0000-0000-000000000001"):
    """
    List all unique files in the knowledge base for a tenant.
    
    Groups by source filename and counts chunks.
    """
    tenant_uuid = resolve_tenant_uuid(tenant_id)
    supabase = get_supabase()
    
    try:
        result = supabase.table("knowledge_base").select("id, category, metadata").eq("tenant_id", tenant_uuid).execute()
        
        # Group by source filename
        files_map: dict[str, dict] = {}
        for item in result.data:
            metadata = item.get("metadata", {})
            if isinstance(metadata, dict):
                source = metadata.get("source", "")
                if source:
                    if source not in files_map:
                        files_map[source] = {
                            "filename": source,
                            "chunks": 0,
                            "category": item.get("category", "manual")
                        }
                    files_map[source]["chunks"] += 1
        
        files = [KnowledgeFile(**f) for f in files_map.values()]
        
        return ListKnowledgeResponse(success=True, files=files)
        
    except Exception as e:
        logger.error(f"Failed to list knowledge files: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


"""
Cliente Supabase para o projeto Nouvaris.

Usa chamadas HTTP diretas com httpx em vez do SDK completo,
evitando dependências de compilação C no Windows.

Usa SERVICE_ROLE_KEY (não ANON_KEY) pois RLS está habilitado.
"""

import os
from functools import lru_cache
from typing import Any, Optional

import logging
import httpx

logger = logging.getLogger(__name__)


class SupabaseClient:
    """
    Cliente simplificado para Supabase usando REST API direta.
    
    Evita o SDK oficial que tem dependências pesadas (pyroaring)
    que requerem compilação C++ no Windows.
    """
    
    def __init__(self, url: str, key: str) -> None:
        """
        Inicializa cliente Supabase.
        
        Args:
            url: URL do projeto Supabase (ex: https://xxx.supabase.co)
            key: Service role key (não anon key)
        """
        self.url = url.rstrip("/")
        self.key = key
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
    
    def table(self, table_name: str) -> "TableQuery":
        """
        Inicia uma query em uma tabela.
        
        Args:
            table_name: Nome da tabela
            
        Returns:
            TableQuery para encadear operações
        """
        return TableQuery(self, table_name)
    
    @property
    def storage(self) -> "StorageClient":
        """Acesso ao Storage."""
        return StorageClient(self)


class StorageClient:
    def __init__(self, client: SupabaseClient):
        self.client = client
        
    def from_(self, bucket_id: str) -> "StorageBucket":
        return StorageBucket(self.client, bucket_id)


class TableQuery:
    """Query builder para tabelas Supabase."""
    
    def __init__(self, client: SupabaseClient, table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self._filters: list[tuple[str, str, Any]] = []
        self._select_cols = "*"
        self._single = False
        self._order_by: Optional[tuple[str, bool]] = None
        self._limit_val: Optional[int] = None
        self._insert_data: Optional[dict] = None
        self._update_data: Optional[dict] = None
        self._delete = False
        self._count_mode: Optional[str] = None
    
    def select(self, columns: str = "*", count: Optional[str] = None) -> "TableQuery":
        """Define colunas a selecionar."""
        self._select_cols = columns
        self._count_mode = count
        return self
    
    def eq(self, column: str, value: Any) -> "TableQuery":
        """Adiciona filtro de igualdade."""
        self._filters.append((column, "eq", value))
        return self
    
    def ilike(self, column: str, value: Any) -> "TableQuery":
        """Adiciona filtro case-insensitive like."""
        self._filters.append((column, "ilike", value))
        return self
    
    def gt(self, column: str, value: Any) -> "TableQuery":
        """Adiciona filtro greater than."""
        self._filters.append((column, "gt", value))
        return self

    def gte(self, column: str, value: Any) -> "TableQuery":
        """Adiciona filtro greater than or equal."""
        self._filters.append((column, "gte", value))
        return self

    def lt(self, column: str, value: Any) -> "TableQuery":
        """Adiciona filtro less than."""
        self._filters.append((column, "lt", value))
        return self

    def lte(self, column: str, value: Any) -> "TableQuery":
        """Adiciona filtro less than or equal."""
        self._filters.append((column, "lte", value))
        return self

    def in_(self, column: str, values: list[Any]) -> "TableQuery":
        """Adiciona filtro IN."""
        val_str = f"({','.join(str(v) for v in values)})"
        self._filters.append((column, "in", val_str))
        return self
    
    def order(self, column: str, ascending: bool = True) -> "TableQuery":
        """Define ordenação."""
        self._order_by = (column, ascending)
        return self
    
    def limit(self, count: int) -> "TableQuery":
        """Define limite de resultados."""
        self._limit_val = count
        return self
    
    def is_(self, column: str, value: str) -> "TableQuery":
        """Adiciona filtro IS (para null checks)."""
        self._filters.append((column, "is", value))
        return self
    
    def single(self) -> "TableQuery":
        """Indica que espera apenas um resultado."""
        self._single = True
        return self
    
    def insert(self, data: dict | list[dict]) -> "TableQuery":
        """Prepara inserção de dados."""
        self._insert_data = data
        return self
    
    def update(self, data: dict) -> "TableQuery":
        """Prepara atualização de dados."""
        self._update_data = data
        return self
    
    def delete(self) -> "TableQuery":
        """Prepara deleção de dados."""
        self._delete = True
        return self
    
    async def execute_async(self) -> "QueryResponse":
        """Executa a query de forma assíncrona (apenas SELECT por enquanto)."""
        if self._insert_data is not None:
            raise NotImplementedError("Async Insert not implemented yet")
        elif self._update_data is not None:
            raise NotImplementedError("Async Update not implemented yet")
        elif self._delete:
            raise NotImplementedError("Async Delete not implemented yet")
        else:
            return await self._execute_select_async()

    def execute(self) -> "QueryResponse":
        """Executa a query (SELECT, INSERT, UPDATE ou DELETE)."""
        if self._insert_data is not None:
            return self._execute_insert()
        elif self._update_data is not None:
            return self._execute_update()
        elif self._delete:
            return self._execute_delete()
        else:
            return self._execute_select()
    
    async def _execute_select_async(self) -> "QueryResponse":
        """Executa SELECT assíncrono."""
        url = f"{self.client.url}/rest/v1/{self.table_name}"
        
        params: dict[str, str] = {"select": self._select_cols}
        for col, op, val in self._filters:
            params[col] = f"{op}.{val}"
        
        if self._order_by:
            col, asc = self._order_by
            params["order"] = f"{col}.{'asc' if asc else 'desc'}"
        
        if self._single and not self._limit_val:
            params["limit"] = "1"
        elif self._limit_val:
            params["limit"] = str(self._limit_val)
        
        headers = dict(self.client.headers)
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
        
        data = response.json()
        return QueryResponse(data)

    def _execute_select(self) -> "QueryResponse":
        """Executa SELECT."""
        url = f"{self.client.url}/rest/v1/{self.table_name}"
        
        params: dict[str, str] = {"select": self._select_cols}
        for col, op, val in self._filters:
            params[col] = f"{op}.{val}"
        
        if self._order_by:
            col, asc = self._order_by
            params["order"] = f"{col}.{'asc' if asc else 'desc'}"
        
        if self._single and not self._limit_val:
            params["limit"] = "1"
        elif self._limit_val:
            params["limit"] = str(self._limit_val)
        
        headers = dict(self.client.headers)
        
        # Add count preference if requested
        if self._count_mode:
            current_prefer = headers.get("Prefer", "")
            params_prefer = f"count={self._count_mode}"
            if current_prefer:
                headers["Prefer"] = f"{current_prefer},{params_prefer}"
            else:
                headers["Prefer"] = params_prefer
        
        response = httpx.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Parse count from Content-Range header
        content_range = response.headers.get("Content-Range")
        count = None
        if content_range and "/" in content_range:
            try:
                total = content_range.split("/")[-1]
                if total != "*":
                    count = int(total)
            except ValueError:
                pass
                
        return QueryResponse(data, count=count)
    
    def _execute_insert(self) -> "QueryResponse":
        """Executa INSERT."""
        url = f"{self.client.url}/rest/v1/{self.table_name}"
        
        headers = dict(self.client.headers)
        headers["Prefer"] = "return=representation"
        
        data = self._insert_data
        if not isinstance(data, list):
            data = [data]
        
        response = httpx.post(url, json=data, headers=headers, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        return QueryResponse(result)
    
    def _execute_update(self) -> "QueryResponse":
        """Executa UPDATE."""
        url = f"{self.client.url}/rest/v1/{self.table_name}"
        
        params: dict[str, str] = {}
        for col, op, val in self._filters:
            params[col] = f"{op}.{val}"
        
        headers = dict(self.client.headers)
        
        response = httpx.patch(url, params=params, json=self._update_data, headers=headers, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        return QueryResponse(result)
    
    def _execute_delete(self) -> "QueryResponse":
        """Executa DELETE."""
        url = f"{self.client.url}/rest/v1/{self.table_name}"
        
        params: dict[str, str] = {}
        for col, op, val in self._filters:
            params[col] = f"{op}.{val}"
        
        headers = dict(self.client.headers)
        
        response = httpx.delete(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        try:
            result = response.json()
        except Exception:
            result = []
        return QueryResponse(result)
    
    def upsert(self, data: dict, on_conflict: Optional[str] = None) -> "TableQuery":
        """Prepara upsert."""
        self._upsert_data = data
        self._on_conflict = on_conflict
        return self
    
    def execute_upsert(self) -> "QueryResponse":
        """Executa upsert."""
        url = f"{self.client.url}/rest/v1/{self.table_name}"
        
        headers = dict(self.client.headers)
        headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        
        params = {}
        if hasattr(self, '_on_conflict') and self._on_conflict:
            params["on_conflict"] = self._on_conflict
        
        response = httpx.post(
            url,
            params=params,
            json=self._upsert_data if isinstance(self._upsert_data, list) else [self._upsert_data],
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        return QueryResponse(response.json())


class StorageBucket:
    """Cliente para operações em bucket do Storage."""
    
    def __init__(self, client: SupabaseClient, bucket_id: str) -> None:
        self.client = client
        self.bucket_id = bucket_id
    
    def upload(self, path: str, file: bytes, content_type: str = "application/octet-stream", upsert: str = "false") -> "QueryResponse":
        """Upload arquivo para o bucket."""
        url = f"{self.client.url}/storage/v1/object/{self.bucket_id}/{path}"
        
        headers = dict(self.client.headers)
        headers["Content-Type"] = content_type
        headers["x-upsert"] = upsert
        
        response = httpx.post(url, content=file, headers=headers, timeout=30)
        
        if response.status_code not in (200, 201):
            try:
                err = response.json()
            except:
                err = response.text
            logger.error(f"Storage Upload Failed: {response.status_code} - {err}")
            response.raise_for_status()
             
        return QueryResponse(response.json())

    def get_public_url(self, path: str) -> str:
        """Retorna URL pública do arquivo."""
        return f"{self.client.url}/storage/v1/object/public/{self.bucket_id}/{path}"


class QueryResponse:
    """Resposta de uma query Supabase."""
    
    def __init__(self, data: Any, count: Optional[int] = None) -> None:
        if isinstance(data, list):
            self.data = data
        elif isinstance(data, dict):
            self.data = [data]
        else:
            self.data = []
        self.count = count


@lru_cache(maxsize=1)
def get_supabase() -> SupabaseClient:
    """
    Retorna cliente Supabase singleton.
    
    Uses SERVICE_ROLE_KEY to bypass RLS for server-side operations.
    
    Returns:
        SupabaseClient instance
        
    Raises:
        ValueError: If SUPABASE_URL or SUPABASE_SERVICE_KEY not set
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not url or not key:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment variables"
        )
    
    return SupabaseClient(url, key)

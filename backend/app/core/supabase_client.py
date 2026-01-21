"""
Cliente Supabase para o projeto Nouvaris.

Usa chamadas HTTP diretas com httpx em vez do SDK completo,
evitando dependências de compilação C no Windows.

Usa SERVICE_ROLE_KEY (não ANON_KEY) pois RLS está habilitado.
"""

import os
from functools import lru_cache
from typing import Any, Optional

import httpx


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
    
    def select(self, columns: str = "*") -> "TableQuery":
        """Define colunas a selecionar."""
        self._select_cols = columns
        return self
    
    def eq(self, column: str, value: Any) -> "TableQuery":
        """Adiciona filtro de igualdade."""
        self._filters.append((column, "eq", value))
        return self
    
    def ilike(self, column: str, value: Any) -> "TableQuery":
        """Adiciona filtro case-insensitive like."""
        self._filters.append((column, "ilike", value))
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
    
    def execute(self) -> "QueryResponse":
        """Executa a query (SELECT, INSERT ou UPDATE)."""
        if self._insert_data is not None:
            return self._execute_insert()
        elif self._update_data is not None:
            return self._execute_update()
        else:
            return self._execute_select()
    
    def _execute_select(self) -> "QueryResponse":
        """Executa SELECT."""
        url = f"{self.client.url}/rest/v1/{self.table_name}"
        
        params: dict[str, str] = {"select": self._select_cols}
        for col, op, val in self._filters:
            params[col] = f"{op}.{val}"
        
        if self._order_by:
            col, asc = self._order_by
            params["order"] = f"{col}.{'asc' if asc else 'desc'}"
        
        # Use limit=1 for single() instead of special Accept header
        if self._single and not self._limit_val:
            params["limit"] = "1"
        elif self._limit_val:
            params["limit"] = str(self._limit_val)
        
        headers = dict(self.client.headers)
        
        response = httpx.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        # Pass raw data to QueryResponse, which now handles dict->list conversion
        return QueryResponse(data)
    
    def _execute_insert(self) -> "QueryResponse":
        """Executa INSERT."""
        url = f"{self.client.url}/rest/v1/{self.table_name}"
        
        headers = dict(self.client.headers)
        
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
        
        # Add on_conflict parameter if specified
        params = {}
        if hasattr(self, '_on_conflict') and self._on_conflict:
            params["on_conflict"] = self._on_conflict
        
        response = httpx.post(
            url,
            params=params,
            json=self._upsert_data if isinstance(self._upsert_data, list) else [self._upsert_data],
            headers=headers,
            timeout=30  # Increased timeout for embedding operations
        )
        response.raise_for_status()
        
        return QueryResponse(response.json())


class QueryResponse:
    """Resposta de uma query Supabase."""
    
    def __init__(self, data: Any) -> None:
        if isinstance(data, list):
            self.data = data
        elif isinstance(data, dict):
            self.data = [data]
        else:
            self.data = []


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

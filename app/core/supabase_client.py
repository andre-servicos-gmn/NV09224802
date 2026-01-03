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
    
    def select(self, columns: str = "*") -> "TableQuery":
        """Define colunas a selecionar."""
        self._select_cols = columns
        return self
    
    def eq(self, column: str, value: Any) -> "TableQuery":
        """Adiciona filtro de igualdade."""
        self._filters.append((column, "eq", value))
        return self
    
    def single(self) -> "TableQuery":
        """Indica que espera apenas um resultado."""
        self._single = True
        return self
    
    def execute(self) -> "QueryResponse":
        """Executa a query."""
        url = f"{self.client.url}/rest/v1/{self.table_name}"
        
        params = {"select": self._select_cols}
        for col, op, val in self._filters:
            params[col] = f"{op}.{val}"
        
        headers = dict(self.client.headers)
        if self._single:
            headers["Accept"] = "application/vnd.pgrst.object+json"
        
        response = httpx.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        return QueryResponse(data if self._single else data)
    
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
        
        response = httpx.post(
            url,
            json=self._upsert_data if isinstance(self._upsert_data, list) else [self._upsert_data],
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        
        return QueryResponse(response.json())


class QueryResponse:
    """Resposta de uma query Supabase."""
    
    def __init__(self, data: Any) -> None:
        self.data = data


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

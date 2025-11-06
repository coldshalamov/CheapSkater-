"""Custom exception types for CheapSkater."""

from __future__ import annotations

from typing import Optional


class SelectorChangedError(Exception):
    """Raised when expected DOM selectors change and scraping fails."""

    def __init__(
        self,
        message: str = "Selectors appear to have changed.",
        *,
        url: Optional[str] = None,
        zip_code: Optional[str] = None,
        category: Optional[str] = None,
    ) -> None:
        self.message = message
        self.url = url
        self.zip_code = zip_code
        self.category = category
        super().__init__(message)

    def __str__(self) -> str:
        context_parts: list[str] = []
        if self.url:
            context_parts.append(f"url={self.url}")
        if self.zip_code:
            context_parts.append(f"zip={self.zip_code}")
        if self.category:
            context_parts.append(f"category={self.category}")
        context = ", ".join(context_parts)
        return f"{self.message} ({context})" if context else self.message


class StoreContextError(Exception):
    """Raised when the store context cannot be set for a retailer."""

    def __init__(
        self,
        message: str = "Unable to set store context.",
        *,
        url: Optional[str] = None,
        zip_code: Optional[str] = None,
        category: Optional[str] = None,
    ) -> None:
        self.message = message
        self.url = url
        self.zip_code = zip_code
        self.category = category
        super().__init__(message)

    def __str__(self) -> str:
        context_parts: list[str] = []
        if self.url:
            context_parts.append(f"url={self.url}")
        if self.zip_code:
            context_parts.append(f"zip={self.zip_code}")
        if self.category:
            context_parts.append(f"category={self.category}")
        context = ", ".join(context_parts)
        return f"{self.message} ({context})" if context else self.message


class PageLoadError(Exception):
    """Raised when a page fails to load or render correctly."""

    def __init__(
        self,
        message: str = "Failed to load page.",
        *,
        url: Optional[str] = None,
        zip_code: Optional[str] = None,
        category: Optional[str] = None,
    ) -> None:
        self.message = message
        self.url = url
        self.zip_code = zip_code
        self.category = category
        super().__init__(message)

    def __str__(self) -> str:
        context_parts: list[str] = []
        if self.url:
            context_parts.append(f"url={self.url}")
        if self.zip_code:
            context_parts.append(f"zip={self.zip_code}")
        if self.category:
            context_parts.append(f"category={self.category}")
        context = ", ".join(context_parts)
        return f"{self.message} ({context})" if context else self.message

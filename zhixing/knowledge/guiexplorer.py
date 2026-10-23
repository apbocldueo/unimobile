"""Lazy client for the official GUI-explorer image-knowledge retrieval service."""

import time

from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="knowledge", name="guiexplorer_retrieval")
class GUIExplorerRetrieval:
    """Reuse the author's SigLIP/FAISS service instead of replacing its algorithm."""

    def __init__(self, endpoint: str | None = None) -> None:
        """Retain configuration without reading files, resolving secrets or connecting.

        Args:
            endpoint: Official RAG service base URL, or RAG_SERVER_ENDPOINT at invocation.
        Returns:
            None.
        """
        self.endpoint = endpoint

    def retrieve_batch(self, paths, *, top_k, threshold, package_name):
        """Submit the exact original image/package/top-k/threshold request with three tries.

        Args:
            paths: Ordered lossless source element-crop paths.
            top_k: Original maximum number of hints per element.
            threshold: Original similarity cutoff.
            package_name: Current original App package for server-side bank/fusion selection.
        Raises:
            Exception: Source encoding or all three original request attempts fail.
        Returns:
            list: Original results, allowing fewer rows just as the source zip does.
        """
        import os
        import requests
        from PIL import Image
        from zhixing.plugins.agent.guiexplorer.source import pil_to_webp_base64

        queries = []
        for path in paths:
            with Image.open(path) as image:
                queries.append(pil_to_webp_base64(image))
        payload = {"package_name": package_name, "queries": queries, "top_k": top_k, "threshold": threshold}
        endpoint = self.endpoint or os.getenv("RAG_SERVER_ENDPOINT", "http://localhost:8769")
        for attempt in range(3):
            try:
                return requests.post(endpoint.rstrip("/") + "/retrieval_batch", json=payload, timeout=300).json()["results"]
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1)

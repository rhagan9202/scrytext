"""Base adapter abstract class for all data source adapters."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from ..schemas.payload import IngestionMetadata, IngestionPayload, ValidationResult


class BaseAdapter(ABC):
    """
    Abstract base class for all data source adapters.

    Each adapter must implement collect(), validate(), and transform() methods
    to handle data from specific source types.
    """

    def __init__(self, config: dict[str, Any]):
        """
        Initialize the adapter with configuration.

        Args:
            config: Adapter-specific configuration dictionary
        """
        self.config = config
        self.source_id = config.get("source_id", "unknown")
        self.use_cloud_processing = config.get("use_cloud_processing", False)

    @abstractmethod
    async def collect(self) -> Any:
        """
        Collect raw data from the source.

        Returns:
            Raw data from the source (format depends on adapter type)

        Raises:
            CollectionError: If data collection fails
        """
        pass

    @abstractmethod
    async def validate(self, raw_data: Any) -> ValidationResult:
        """
        Validate the collected raw data.

        Args:
            raw_data: Raw data from collect() method

        Returns:
            ValidationResult with quality metrics and error flags
        """
        pass

    @abstractmethod
    async def transform(self, raw_data: Any) -> Any:
        """
        Transform raw data into standardized format.

        Args:
            raw_data: Raw data from collect() method

        Returns:
            Transformed data (cleaned text, JSON, or DataFrame)
        """
        pass

    async def process(self) -> IngestionPayload:
        """
        Execute the full ingestion pipeline: collect, validate, transform.

        Returns:
            IngestionPayload with data, metadata, and validation results
        """
        start_time = datetime.now(timezone.utc)

        # Collect raw data
        raw_data = await self.collect()

        # Validate data
        validation = await self.validate(raw_data)

        # Transform data
        transformed_data = await self.transform(raw_data)

        # Build metadata as IngestionMetadata object
        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        metadata = IngestionMetadata(
            source_id=self.source_id,
            adapter_type=self.__class__.__name__,
            timestamp=start_time.isoformat(),
            processing_duration_ms=duration_ms,
            processing_mode="cloud" if self.use_cloud_processing else "local",
            correlation_id=self.config.get("correlation_id"),
        )

        return IngestionPayload(data=transformed_data, metadata=metadata, validation=validation)

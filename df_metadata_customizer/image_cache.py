"""Image cache with optimized resizing for cover images."""

from PIL import Image


class OptimizedImageCache:
    """Optimized cache for cover images with pre-resized versions."""

    def __init__(self, max_size: int = 100) -> None:
        self.max_size = max_size
        self._cache = {}
        self._access_order = []
        self._resized_cache = {}  # Cache for pre-resized images

    def get(self, key, size=None):
        """Get image from cache, optionally resized."""
        if key not in self._cache:
            return None

        # Update access order
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

        img = self._cache[key]

        # Return pre-resized version if available and size matches
        if size:
            resize_key = f"{key}_{size[0]}_{size[1]}"
            if resize_key in self._resized_cache:
                return self._resized_cache[resize_key]

            # Create and cache resized version
            resized = self._resize_image_optimized(img, size)
            self._resized_cache[resize_key] = resized
            return resized

        return img

    def put(self, key, image):
        """Add image to cache with LRU eviction."""
        if key in self._cache:
            self._access_order.remove(key)

        self._cache[key] = image
        self._access_order.append(key)

        # Evict least recently used if over size limit
        while len(self._cache) > self.max_size:
            oldest_key = self._access_order.pop(0)
            # Also remove resized versions
            for resize_key in list(self._resized_cache.keys()):
                if resize_key.startswith(f"{oldest_key}_"):
                    del self._resized_cache[resize_key]
            del self._cache[oldest_key]

    def _resize_image_optimized(self, img, size):
        """Optimized image resizing with quality/speed balance."""
        if img.size == size:
            return img

        # Use faster resampling for better performance
        return img.resize(size, Image.Resampling.NEAREST)

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._resized_cache.clear()
        self._access_order.clear()

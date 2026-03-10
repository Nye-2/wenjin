"""ViewImageMiddleware - injects viewed images into conversation for vision models.

When the model supports vision (supports_vision=True) and there are viewed_images
in state, this middleware injects them as HumanMessage with image content before
the model processes messages.

After model processing, the viewed_images are cleared to prevent re-injection.
"""

from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState


class ViewImageMiddleware(Middleware):
    """Middleware that injects viewed images for vision-enabled models.

    Behavior:
    - before_model: If supports_vision and viewed_images exist, creates a
      HumanMessage with image content for each viewed image
    - after_model: Clears viewed_images to prevent re-injection in future turns

    Condition:
    - Only processes when config.configurable.supports_vision == True
    - Only processes when state.viewed_images is non-empty
    """

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Inject viewed images as HumanMessage content.

        Args:
            state: Current thread state containing viewed_images
            config: Runtime configuration with supports_vision flag

        Returns:
            Dict with messages containing image content, or empty dict if
            conditions are not met
        """
        # Check if vision is supported
        configurable = config.get("configurable", {})
        supports_vision = configurable.get("supports_vision", False)

        if not supports_vision:
            return {}

        # Check if there are viewed images
        viewed_images = state.get("viewed_images")
        if not viewed_images:
            return {}

        # Build image content list
        image_content: list[dict[str, Any]] = []
        for image_name, image_data in viewed_images.items():
            image_url = {
                "url": f"data:{image_data['mime_type']};base64,{image_data['base64']}",
            }
            image_content.append({
                "type": "image_url",
                "image_url": image_url,
            })

        # Create HumanMessage with image content
        message = HumanMessage(content=image_content)

        return {"messages": [message]}

    async def after_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        """Clear viewed_images after model processing.

        Args:
            state: Current thread state
            config: Runtime configuration

        Returns:
            Dict with empty viewed_images to clear the state
        """
        # Always clear viewed_images after model processes them
        return {"viewed_images": {}}

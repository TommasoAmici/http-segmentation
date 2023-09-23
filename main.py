import enum
import os
import uuid
from datetime import datetime
from http import HTTPStatus
from io import BytesIO
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

if TYPE_CHECKING:
    from PIL.Image import Image

KILL_AFTER_SECONDS = 120

s3_config = {
    "endpoint": os.environ["S3_ENDPOINT_URL"],
    "bucket": os.environ["S3_BUCKET"],
    "aws_access_key_id": os.environ["S3_ACCESS_KEY"],
    "aws_secret_access_key": os.environ["S3_SECRET_KEY"],
}

# global variable used to kill the container if no requests have been received
# in the last KILL_AFTER_SECONDS seconds
time_of_last_request = None


class ReturnType(enum.Enum):
    NO_MASK = 1
    SEGMENTED_IMAGE = 2
    ERROR = 3


class Segmentator:
    def __init__(self, image: "Image", resize: int | None = None) -> None:
        self.image = image
        self.resize = resize

    def crop(self):
        from rembg import new_session, remove

        output: "Image" = remove(
            self.image,
            session=new_session(os.environ.get("MODEL", "silueta")),
            alpha_matting=True,
            alpha_matting_foreground_threshold=270,
            alpha_matting_background_threshold=20,
            alpha_matting_erode_size=11,
            post_process_mask=True,
        )
        # Find the bounding box of the masked region
        bbox = output.getbbox()

        # Crop the image based on the bounding box
        segmented_image = output.crop(bbox)
        return segmented_image

    def resize_image(self, image):
        if not self.resize:
            return image

        image.thumbnail((self.resize, self.resize))
        if image.width != self.resize or image.height != self.resize:
            if image.width > image.height:
                width = self.resize
                height = int((self.resize / image.width) * image.height)
            else:
                width = int((self.resize / image.height) * image.width)
                height = self.resize
            image = image.resize((width, height))
        return image

    def segment(self):
        result = self.crop()
        resized = self.resize_image(result)
        return resized


async def segment_handler(request: Request):
    """
    This handler takes an image as input, finds all objects in the image, and
    returns a zip file containing cropped images of each object.
    If only one object is found, it returns a single image instead of a zip
    file.

    If a resize parameter is passed, it resizes the cropped images to the
    specified size while maintaining the aspect ratio.

    Examples:
        curl -X POST --data-binary "@/path/to/image.jpg" http://localhost:8000/segment
        curl -X POST --data-binary "@/path/to/image.jpg" http://localhost:8000/segment/512
    """
    import boto3
    from PIL import Image

    resize = request.path_params.get("resize", None)

    global time_of_last_request
    time_of_last_request = datetime.utcnow()

    body = await request.body()
    image = Image.open(BytesIO(body))
    segmentator = Segmentator(image, resize)
    segmented = segmentator.segment()

    # If all masks errored out, return an error
    if not segmented:
        return JSONResponse(
            {"error": "Error cropping image"},
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    s3_client = boto3.client(
        "s3",
        endpoint_url=s3_config["endpoint"],
        aws_access_key_id=s3_config["aws_access_key_id"],
        aws_secret_access_key=s3_config["aws_secret_access_key"],
        aws_session_token=None,
    )

    bytes_stream = BytesIO()
    segmented.save(bytes_stream, "WEBP")
    bytes_stream.seek(0)
    file_name = uuid.uuid4().hex + ".webp"
    s3_client.upload_fileobj(bytes_stream, s3_config["bucket"], file_name)
    return JSONResponse(
        {
            "file_names": [
                os.path.join(s3_config["endpoint"], s3_config["bucket"], file_name)
            ]
        }
    )


async def health_handler(request: Request):
    """
    This is somewhat of a weird health check handler. If no requests have been
    received in the last KILL_AFTER_SECONDS seconds, it returns an error and
    forces the container to restart. Otherwise, it returns a 200 OK.

    This is because the AI model is loaded into memory only when a request is
    received, and we want to free memory after a period of inactivity, since
    I don't expect this service to be used very often.
    """
    global time_of_last_request

    if time_of_last_request is None:
        return Response(status_code=HTTPStatus.OK)

    time_since_last_request = datetime.utcnow() - time_of_last_request
    if time_since_last_request.total_seconds() > KILL_AFTER_SECONDS:
        return Response(status_code=HTTPStatus.INTERNAL_SERVER_ERROR)

    return Response(status_code=HTTPStatus.OK)


app = Starlette(
    debug=False,
    routes=[
        Route("/health", health_handler),
        Route("/segment", segment_handler, methods=["POST"]),
        Route("/segment/{resize:int}", segment_handler, methods=["POST"]),
    ],
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)

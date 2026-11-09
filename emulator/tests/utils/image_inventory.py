"""Stateful hermetic image API/process boundary for isolation regressions."""

from types import SimpleNamespace

from docker.errors import NotFound

from tests.utils.helpers import RUN_LABEL

IMAGE_ID = "sha256:" + "a" * 64


class ImageInventory:
    def __init__(self, run_id):
        self.run_id = run_id
        self.tags = {}
        self.calls = []
        self.failure = None
        self.foreign_alias = "localhost/sentinel:keep"
        self.references = {"foreign-container": IMAGE_ID}
        self.image = SimpleNamespace(
            id=IMAGE_ID,
            attrs={
                "RepoTags": [self.foreign_alias],
                "Config": {"Labels": {RUN_LABEL: run_id}},
            },
            reload=lambda: None,
        )

    def get(self, tag):
        self.calls.append(("inspect", tag))
        if tag not in self.tags:
            raise NotFound("absent exact tag")
        return self.tags[tag]

    def build(self, **kwargs):
        self.calls.append(("build", kwargs))
        tag = kwargs["tag"]
        self.tags[tag] = self.image
        self.image.attrs["RepoTags"].append(tag)
        if self.failure:
            raise self.failure
        return self.image, []

    def command(self, args, *, endpoint=None):
        self.calls.append(("command", args, endpoint))
        assert args[0] == "untag"
        assert len(args) == 3
        image_id, tag = args[1:]
        assert image_id == IMAGE_ID
        self.tags.pop(tag)
        self.image.attrs["RepoTags"].remove(tag)
        return ""

    def client(self):
        empty = SimpleNamespace(list=lambda **kwargs: [])
        return SimpleNamespace(
            images=self, containers=empty, networks=empty, volumes=empty
        )

import typing


class Target(typing.TypedDict):
    targets: typing.List[str]
    labels: typing.Dict[str, str]


TargetList = typing.List[Target]

import typing


class Target:
    targets: typing.List[str]
    labels: typing.Dict[str, str]


TargetList = typing.List[Target]

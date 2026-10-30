import secrets

WORDS = ("river lamp orange seven tiger cloud maple stone rocket honey violet anchor pepper meadow falcon button copper garden "
         "island jungle kettle lemon marble nickel olive planet quartz ribbon saddle thunder umbrella velvet walnut yellow zebra "
         "acorn bridge candle dragon ember forest glacier harbor ivory jasmine koala lantern mango nectar oasis pebble quiver "
         "raven spruce tulip valley willow coral breeze cactus dune echo fern grove hazel iris lotus").split()


def phrase(n=3):
    out = []
    while len(out) < n:
        w = secrets.choice(WORDS)
        if w not in out:
            out.append(w)
    return " ".join(out)

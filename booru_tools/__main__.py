from booru_tools.core import BooruTools

booru_tools = BooruTools()
booru_tools.sync(
    urls=[
        "https://e621.net/posts/3052115",
        # "https://e621.net/pools/36579",
        # "https://e621.net/posts/1150307",
        # "https://e621.net/pools/36579",
        "https://e621.net/posts?tags=claweddrip+female+-male_on_male",
    ]
)
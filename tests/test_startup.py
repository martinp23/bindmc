from nicegui.testing import User

pytest_plugins = ["nicegui.testing.user_plugin"]


async def test_startup(user: User) -> None:
    # Set up test data

    await user.open("/")
    await user.should_see("BindMC")
    user.find("Simulate").click()
    user.find("Define model").click()

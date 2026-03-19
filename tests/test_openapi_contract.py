def test_public_openapi_paths_are_small_and_read_only(client) -> None:
    paths = client.app.openapi()["paths"]
    assert set(paths.keys()) == {
        "/health",
        "/datasets",
        "/datasets/{dataset_name}/documents",
        "/search_dataset",
        "/search_all",
    }


def test_public_openapi_does_not_expose_download_route(client) -> None:
    paths = client.app.openapi()["paths"]
    assert "/_downloads/{token}" not in paths


def test_search_dataset_schema_does_not_expose_dataset_id(client) -> None:
    schema = client.app.openapi()["components"]["schemas"]["SearchDatasetRequest"]
    properties = schema["properties"]
    assert "dataset_name" in properties
    assert "dataset_id" not in properties


def test_operation_ids_and_descriptions_are_present(client) -> None:
    paths = client.app.openapi()["paths"]
    assert paths["/search_dataset"]["post"]["operationId"] == "searchDataset"
    assert "Prefer searchDataset whenever possible" in paths["/search_all"]["post"]["description"]
    assert "Admin/debug only" in paths["/health"]["get"]["description"]

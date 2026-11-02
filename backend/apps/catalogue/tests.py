from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import Department, Role, User
from apps.catalogue.models import Location, Resource, ResourceType


class CatalogueModelTest(APITestCase):
    def test_resource_type_slug_generation(self):
        rt = ResourceType.objects.create(name="Advanced Robotics Lab")
        self.assertEqual(rt.slug, "advanced-robotics-lab")
        self.assertTrue(rt.requires_checkin)

    def test_location_string_representation(self):
        loc = Location.objects.create(building="Block 34", floor="3", room="301")
        self.assertEqual(str(loc), "Block 34 · Floor 3 · 301")

        loc_no_floor = Location.objects.create(building="Auditorium", room="Main Hall")
        self.assertEqual(str(loc_no_floor), "Auditorium · Main Hall")

    def test_resource_cover_fallback(self):
        rt = ResourceType.objects.create(name="Lab")
        r = Resource.objects.create(
            code="LAB-101", name="Test Lab", type=rt, image_url="https://images.test/cover.jpg"
        )
        self.assertEqual(r.cover, "https://images.test/cover.jpg")


class ResourceTypeAndLocationApiTest(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="stu", password="pw", role=Role.STUDENT)
        self.custodian = User.objects.create_user(username="cust", password="pw", role=Role.CUSTODIAN)
        self.admin = User.objects.create_user(username="adm", password="pw", role=Role.ADMIN)
        self.rt = ResourceType.objects.create(name="Classroom", color="#123456")

    def test_resource_type_permissions(self):
        # Authenticated users can list resource types
        self.client.force_authenticate(user=self.student)
        r = self.client.get("/api/resource-types")
        self.assertEqual(r.status_code, 200)

        # Student cannot create resource types
        self.client.force_authenticate(user=self.student)
        self.assertEqual(self.client.post("/api/resource-types", {"name": "Lab"}, format="json").status_code, 403)

        # Custodian is not a policy admin -> 403
        self.client.force_authenticate(user=self.custodian)
        self.assertEqual(self.client.post("/api/resource-types", {"name": "Lab"}, format="json").status_code, 403)

        # Admin can create resource types
        self.client.force_authenticate(user=self.admin)
        r = self.client.post("/api/resource-types", {"name": "Auditorium", "color": "#abcdef"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(ResourceType.objects.filter(name="Auditorium").count(), 1)

    def test_location_permissions(self):
        self.client.force_authenticate(user=self.student)
        self.assertEqual(
            self.client.post("/api/locations", {"building": "Block 25", "room": "101"}, format="json").status_code, 403
        )

        # Custodian is a manager -> can create location
        self.client.force_authenticate(user=self.custodian)
        r = self.client.post("/api/locations", {"building": "Block 25", "floor": "1", "room": "101"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Location.objects.filter(building="Block 25").count(), 1)


class ResourceApiTest(APITestCase):
    def setUp(self):
        self.dept = Department.objects.create(code="CSE", name="Computer Science")
        self.rtype = ResourceType.objects.create(name="Laboratory", color="#FF0000")
        self.loc = Location.objects.create(building="Block 34", floor="2", room="204")
        self.student = User.objects.create_user(username="stu", password="pw", role=Role.STUDENT)
        self.custodian = User.objects.create_user(username="cust", password="pw", role=Role.CUSTODIAN)

        self.r1 = Resource.objects.create(
            code="LAB-CSE-01",
            name="Cloud Computing Lab",
            type=self.rtype,
            department=self.dept,
            location=self.loc,
            capacity=30,
            features=["AC", "Projector", "Linux"],
            value_inr=500000,
        )
        self.r2 = Resource.objects.create(
            code="LAB-CSE-02",
            name="Hardware Lab",
            type=self.rtype,
            department=self.dept,
            location=self.loc,
            capacity=15,
            features=["Soldering", "Oscilloscope"],
            value_inr=200000,
        )

    def test_list_and_search_filters(self):
        self.client.force_authenticate(user=self.student)

        # List all
        r = self.client.get("/api/resources")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 2)

        # Search by query
        r = self.client.get("/api/resources?q=Cloud")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]["code"], "LAB-CSE-01")

        # Filter by minimum capacity
        r = self.client.get("/api/resources?min_capacity=20")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]["code"], "LAB-CSE-01")

        # Filter by building
        r = self.client.get("/api/resources?building=Block%2034")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 2)

        # Filter by features
        r = self.client.get("/api/resources?features=Soldering")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]["code"], "LAB-CSE-02")

    def test_facets_endpoint(self):
        self.client.force_authenticate(user=self.student)
        r = self.client.get("/api/resources/facets")
        self.assertEqual(r.status_code, 200)
        self.assertIn("types", r.data)
        self.assertIn("departments", r.data)
        self.assertIn("buildings", r.data)
        self.assertIn("features", r.data)
        self.assertEqual(r.data["max_capacity"], 30)

    def test_create_and_update_permissions(self):
        self.client.force_authenticate(user=self.student)
        # Student cannot create resource
        payload = {
            "code": "LAB-NEW",
            "name": "New Lab",
            "type": self.rtype.id,
            "capacity": 20,
        }
        self.assertEqual(self.client.post("/api/resources", payload, format="json").status_code, 403)

        # Custodian can create resource
        self.client.force_authenticate(user=self.custodian)
        r = self.client.post("/api/resources", payload, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Resource.objects.filter(code="LAB-NEW").count(), 1)

        # Custodian can update resource
        patch_r = self.client.patch(f"/api/resources/{self.r1.id}", {"capacity": 35}, format="json")
        self.assertEqual(patch_r.status_code, 200)
        self.r1.refresh_from_db()
        self.assertEqual(self.r1.capacity, 35)

    def test_qr_and_checkin_token_endpoints(self):
        # QR poster image SVG is readable by authenticated users
        self.client.force_authenticate(user=self.student)
        r = self.client.get(f"/api/resources/{self.r1.id}/qr")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/svg+xml")

        # checkin-token endpoint is restricted to managers
        self.client.force_authenticate(user=self.student)
        self.assertEqual(self.client.get(f"/api/resources/{self.r1.id}/checkin-token").status_code, 403)

        self.client.force_authenticate(user=self.custodian)
        token_r = self.client.get(f"/api/resources/{self.r1.id}/checkin-token")
        self.assertEqual(token_r.status_code, 200)
        self.assertEqual(token_r.data["token"], str(self.r1.checkin_token))


class BulkImportCsvTest(APITestCase):
    def setUp(self):
        self.dept = Department.objects.create(code="CSE", name="Computer Science")
        self.rtype = ResourceType.objects.create(name="Laboratory")
        self.student = User.objects.create_user(username="stu", password="pw", role=Role.STUDENT)
        self.custodian = User.objects.create_user(username="cust", password="pw", role=Role.CUSTODIAN)

    def test_bulk_import_permission(self):
        self.client.force_authenticate(user=self.student)
        self.assertEqual(self.client.post("/api/resources/bulk-import", {"csv": ""}, format="json").status_code, 403)

    def test_bulk_import_valid_csv(self):
        csv_data = """code,name,type,department,building,floor,room,capacity,features,value_inr,image_url,description
LAB-CSV-01,AI Studio,Laboratory,CSE,Block 34,4,402,25,GPU|Workstations,1200000,,AI lab
LAB-CSV-02,Drone Lab,Laboratory,CSE,Block 34,1,105,10,3D Printer|Drones,800000,,Drone studio
"""
        self.client.force_authenticate(user=self.custodian)
        r = self.client.post("/api/resources/bulk-import", {"csv": csv_data}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["created"], 2)
        self.assertEqual(r.data["updated"], 0)
        self.assertEqual(len(r.data["errors"]), 0)

        # Check DB
        self.assertTrue(Resource.objects.filter(code="LAB-CSV-01").exists())
        r1 = Resource.objects.get(code="LAB-CSV-01")
        self.assertEqual(r1.capacity, 25)
        self.assertEqual(r1.features, ["GPU", "Workstations"])
        self.assertEqual(r1.location.building, "Block 34")

    def test_bulk_import_handles_row_errors_gracefully(self):
        # Second row has non-existent resource type "AlienLab"
        csv_data = """code,name,type,department,building,floor,room,capacity,features,value_inr,image_url,description
LAB-OK,Valid Lab,Laboratory,CSE,Block 34,1,101,10,AC,100000,,Good
LAB-BAD,Broken Lab,NonExistentType,CSE,Block 34,1,102,10,AC,100000,,Bad
"""
        self.client.force_authenticate(user=self.custodian)
        r = self.client.post("/api/resources/bulk-import", {"csv": csv_data}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["created"], 1)
        self.assertEqual(len(r.data["errors"]), 1)
        self.assertEqual(r.data["errors"][0]["row"], 3)


class SavedRoomsTest(APITestCase):
    def setUp(self):
        rtype = ResourceType.objects.create(name="Laboratory", color="#FF0000")
        self.room = Resource.objects.create(code="LAB-1", name="Lab One", type=rtype, capacity=10)
        self.other = Resource.objects.create(code="LAB-2", name="Lab Two", type=rtype, capacity=10)
        self.student = User.objects.create_user(username="stu", password="pw", role=Role.STUDENT)
        self.friend = User.objects.create_user(username="fri", password="pw", role=Role.STUDENT)
        self.client.force_authenticate(self.student)

    def test_a_student_can_save_and_unsave_their_own_list(self):
        self.assertEqual(self.client.post(f"/api/resources/{self.room.id}/saved").status_code, 200)
        self.assertEqual(self.client.post(f"/api/resources/{self.room.id}/saved").status_code, 200)  # repeat is harmless

        self.assertEqual([r["id"] for r in self.client.get("/api/resources?saved=1").data], [self.room.id])
        self.assertTrue(self.client.get(f"/api/resources/{self.room.id}").data["is_saved"])
        flags = {r["id"]: r["is_saved"] for r in self.client.get("/api/resources").data}
        self.assertEqual(flags, {self.room.id: True, self.other.id: False})

        self.client.force_authenticate(self.friend)
        self.assertEqual(self.client.get("/api/resources?saved=1").data, [])
        self.assertFalse(self.client.get(f"/api/resources/{self.room.id}").data["is_saved"])

        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.delete(f"/api/resources/{self.room.id}/saved").status_code, 200)
        self.assertEqual(self.client.get("/api/resources?saved=1").data, [])

    def test_saving_needs_sign_in_and_does_not_open_up_editing(self):
        self.assertEqual(self.client.delete(f"/api/resources/{self.room.id}").status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(f"/api/resources/{self.room.id}/saved").status_code, 401)

import io, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import novel_comic as app

class Tests(unittest.TestCase):
    def test_story_validation(self):
        app.validate_story({"panels":[{"prompt":"person walking","caption":"你好"}]})
        for bad in ({},{"panels":[]},{"panels":[{"prompt":""}]}):
            with self.assertRaises(ValueError):app.validate_story(bad)

    def test_workflow_links_and_dimensions(self):
        graph=app.workflow("test",123)
        for node in graph.values():
            for value in node["inputs"].values():
                if isinstance(value,list):
                    self.assertIn(value[0],graph)
        self.assertEqual(graph["9"]["inputs"]["steps"],4)
        self.assertEqual(graph["10"]["inputs"]["width"],768)
        self.assertEqual(graph["2"]["inputs"]["device"],"cpu")

    def test_render_error_propagates(self):
        with patch.object(app,"api",side_effect=[
            {"prompt_id":"job"},
            {"job":{"status":{"status_str":"error","messages":["out of memory"]}}}
        ]):
            with self.assertRaisesRegex(RuntimeError,"out of memory"):app.render("test",1)

    def test_completed_download_is_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"model"
            p.write_bytes(b"correct")
            with patch.object(app.requests,"get") as network:
                app.download("https://example.invalid",p,app.digest(p),7,lambda _:None)
                network.assert_not_called()

    def test_output_images_and_pdf(self):
        data={"characters":"black hair","panels":[{"prompt":"walking","caption":"第一格：你好"},
                                                 {"prompt":"sitting","caption":"第二格：再见"}]}
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(app,"ROOT",Path(tmp)),patch.object(app,"start_ollama"),patch.object(app,"start_comfy"),patch.object(app,"api"),patch.object(app,"render",return_value=Image.new("RGB",(768,1024),"white")):
                out=app.generate(data,"manga",lambda _:None)
            self.assertTrue((out/"comic.pdf").read_bytes().startswith(b"%PDF"))
            self.assertEqual(len(list(out.glob("*-comic.png"))),2)
            self.assertEqual(json.loads((out/"storyboard.json").read_text(encoding="utf-8")),data)

if __name__=="__main__":unittest.main()

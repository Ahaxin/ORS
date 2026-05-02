import { BrowserRouter, Routes, Route } from "react-router-dom";
import NewProject from "./pages/NewProject";
import ProjectPage from "./pages/Project";
import Gallery from "./pages/Gallery";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Gallery />} />
        <Route path="/new" element={<NewProject />} />
        <Route path="/projects/:id" element={<ProjectPage />} />
      </Routes>
    </BrowserRouter>
  );
}

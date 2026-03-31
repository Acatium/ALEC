import { Link, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

const navItems = [
  { path: "/", label: "Engagements" },
  { path: "/engagements/new", label: "New" },
];

export default function Layout({ children }: { children: ReactNode }) {
  const location = useLocation();

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Desktop sidebar */}
      <aside className="hidden md:fixed md:inset-y-0 md:flex md:w-56 md:flex-col">
        <div className="flex min-h-0 flex-1 flex-col border-r border-gray-200 bg-white">
          <div className="flex h-14 items-center px-4 border-b border-gray-200">
            <Link to="/" className="text-lg font-bold text-gray-900">
              ALEC
            </Link>
          </div>
          <nav className="flex-1 space-y-1 px-2 py-3">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={`block rounded-md px-3 py-2 text-sm font-medium ${
                  location.pathname === item.path
                    ? "bg-gray-100 text-gray-900"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </aside>

      {/* Main content */}
      <div className="md:pl-56">
        <main className="px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>

      {/* Mobile bottom tabs */}
      <nav className="fixed inset-x-0 bottom-0 z-10 flex border-t border-gray-200 bg-white md:hidden">
        {navItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={`flex-1 py-3 text-center text-xs font-medium ${
              location.pathname === item.path
                ? "text-blue-600"
                : "text-gray-500"
            }`}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}

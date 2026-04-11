#include "../include/vector3.h"
#include <cmath>
#include <iomanip>
#include <stdexcept>

// Constructors
Vector3::Vector3(double x_, double y_, double z_) : x(x_), y(y_), z(z_) {}

// Basic operations
Vector3 Vector3::operator+(const Vector3& other) const {
    return Vector3(x + other.x, y + other.y, z + other.z);
}

Vector3 Vector3::operator-(const Vector3& other) const {
    return Vector3(x - other.x, y - other.y, z - other.z);
}

Vector3 Vector3::operator-() const {
    return Vector3(-x, -y, -z);
}

Vector3 Vector3::operator*(double scalar) const {
    return Vector3(x * scalar, y * scalar, z * scalar);
}

Vector3 Vector3::operator/(double scalar) const {
    if (std::abs(scalar) < 1e-15) {
        throw std::runtime_error("Division by near-zero in Vector3");
    }
    return Vector3(x / scalar, y / scalar, z / scalar);
}

Vector3& Vector3::operator+=(const Vector3& other) {
    x += other.x;
    y += other.y;
    z += other.z;
    return *this;
}

Vector3& Vector3::operator-=(const Vector3& other) {
    x -= other.x;
    y -= other.y;
    z -= other.z;
    return *this;
}

Vector3& Vector3::operator*=(double scalar) {
    x *= scalar;
    y *= scalar;
    z *= scalar;
    return *this;
}

Vector3& Vector3::operator/=(double scalar) {
    if (std::abs(scalar) < 1e-15) {
        throw std::runtime_error("Division by near-zero in Vector3");
    }
    x /= scalar;
    y /= scalar;
    z /= scalar;
    return *this;
}

// Vector operations
double Vector3::dot(const Vector3& other) const {
    return x * other.x + y * other.y + z * other.z;
}

Vector3 Vector3::cross(const Vector3& other) const {
    return Vector3(
        y * other.z - z * other.y,
        z * other.x - x * other.z,
        x * other.y - y * other.x
    );
}

double Vector3::norm() const {
    return std::sqrt(x * x + y * y + z * z);
}

double Vector3::norm2() const {
    return x * x + y * y + z * z;
}

Vector3 Vector3::normalized() const {
    double n = norm();
    if (n < 1e-15) {
        return Vector3(0, 0, 0);
    }
    return *this / n;
}

// Comparison operators
bool Vector3::operator==(const Vector3& other) const {
    const double eps = 1e-12;
    return (std::abs(x - other.x) < eps &&
        std::abs(y - other.y) < eps &&
        std::abs(z - other.z) < eps);
}

bool Vector3::operator!=(const Vector3& other) const {
    return !(*this == other);
}

// I/O operators
std::ostream& operator<<(std::ostream& os, const Vector3& v) {
    os << std::scientific << std::setprecision(8)
        << "(" << v.x << ", " << v.y << ", " << v.z << ")";
    return os;
}

std::istream& operator>>(std::istream& is, Vector3& v) {
    char c;
    is >> c >> v.x >> c >> v.y >> c >> v.z >> c;
    return is;
}

// Utility methods
void Vector3::set(double x_, double y_, double z_) {
    x = x_;
    y = y_;
    z = z_;
}

void Vector3::zero() {
    x = y = z = 0.0;
}

bool Vector3::isZero() const {
    const double eps = 1e-15;
    return (std::abs(x) < eps && std::abs(y) < eps && std::abs(z) < eps);
}

double Vector3::distanceTo(const Vector3& other) const {
    return (*this - other).norm();
}

double Vector3::angleWith(const Vector3& other) const {
    double cos_angle = dot(other) / (norm() * other.norm());
    // Clamp to [-1, 1] to avoid numerical issues
    cos_angle = std::max(-1.0, std::min(1.0, cos_angle));
    return std::acos(cos_angle);
}

Vector3 Vector3::projectOnto(const Vector3& onto) const {
    double onto_norm2 = onto.norm2();
    if (onto_norm2 < 1e-15) {
        return Vector3(0, 0, 0);
    }
    return onto * (dot(onto) / onto_norm2);
}
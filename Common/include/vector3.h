#ifndef VECTOR3_H
#define VECTOR3_H

#include <iostream>

class Vector3 {
public:
    double x, y, z;

    // Constructors
    Vector3(double x_ = 0.0, double y_ = 0.0, double z_ = 0.0);
    Vector3(const Vector3& other) = default;

    // Basic operations
    Vector3 operator+(const Vector3& other) const;
    Vector3 operator-(const Vector3& other) const;
    Vector3 operator*(double scalar) const;
    Vector3 operator/(double scalar) const;

    Vector3& operator+=(const Vector3& other);
    Vector3& operator-=(const Vector3& other);
    Vector3& operator*=(double scalar);
    Vector3& operator/=(double scalar);

    // Vector operations
    double dot(const Vector3& other) const;
    Vector3 cross(const Vector3& other) const;
    double norm() const;
    double norm2() const;
    Vector3 normalized() const;

    // Comparison
    bool operator==(const Vector3& other) const;
    bool operator!=(const Vector3& other) const;

    // Utility
    void set(double x_, double y_, double z_);
    void zero();
    bool isZero() const;
    double distanceTo(const Vector3& other) const;
    double angleWith(const Vector3& other) const;
    Vector3 projectOnto(const Vector3& onto) const;

    // I/O
    friend std::ostream& operator<<(std::ostream& os, const Vector3& v);
    friend std::istream& operator>>(std::istream& is, Vector3& v);
};

#endif // VECTOR3_H